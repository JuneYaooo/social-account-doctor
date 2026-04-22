#!/usr/bin/env python3
"""
social-account-doctor: analyze_video.py

输入：本地视频路径
输出：JSON — 按内容类型走三条分析路径之一：
  - talking 模式：口播主导 → 全片 ASR + 口播稿分析 + 轻量视觉分段
  - visual 模式：视觉主导 → 现行密集分段视觉拆解（钩子/节奏/情绪）
  - keyframe 模式：图文密集 → ffmpeg 场景变化抽关键帧 + 每帧 Gemini OCR/拆解
  - auto（默认）：抽 5 个代表帧 + 前 30s 音轨喂 Gemini 判 content_type，自动路由

铁律澄清：
  - 「不抽帧」指的是不要对【时序内容】做均匀抽帧 — 钩子/节奏/情绪弧抽帧会丢光
  - 但【图文密集类】（PPT 录屏 / 知识截图视频 / 思维导图）画面是文字稳定载体，
    时序信息少，必须抽场景变化关键帧才能拆出知识点
  - 三条路径都遵循：用 ffmpeg 重编码到 base64 可吞的大小，喂 Gemini 3.1 Pro 原生多模态

环境变量：
  VIDEO_ANALYSIS_API_KEY / VIDEO_ANALYSIS_BASE_URL / VIDEO_ANALYSIS_MODEL_NAME
  AUDIO_TRANSCRIPTION_API_KEY / AUDIO_TRANSCRIPTION_BASE_URL / AUDIO_TRANSCRIPTION_MODEL
    （talking 模式必须设；其他模式可选）

用法：
  analyze_video.py <video_path>                # auto 自动判定
  analyze_video.py <video_path> --mode talking # 强制口播路径
  analyze_video.py <video_path> --mode visual  # 强制视觉路径
  analyze_video.py <video_path> --mode keyframe# 强制关键帧路径
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import requests
except ImportError:
    print(json.dumps({"error": "missing dep: pip install requests"}, ensure_ascii=False))
    sys.exit(1)


# ============ 模式参数 ============
SEGMENT_SECONDS_VISUAL = 90       # visual 模式：每 90s 切段
SEGMENT_SECONDS_TALKING = 180     # talking 模式：稀疏分段（口播为主，视觉做辅助）
AUDIO_CHUNK_SECONDS = 600
AUDIO_MAX_BYTES = 45 * 1024 * 1024
VIDEO_SEGMENT_MAX_BYTES = 18 * 1024 * 1024
KEYFRAME_SCENE_THRESHOLD = 0.30   # ffmpeg scene change 阈值
DETECTION_FRAME_COUNT = 5         # auto detection 抽 5 帧
DETECTION_AUDIO_SECONDS = 30      # auto detection 截前 30s 音轨

# 关键帧上限 — 按时长动态
def keyframe_cap(duration: float) -> int:
    if duration <= 180:
        return 10
    if duration <= 600:
        return 20
    return 30


# ============ Prompt ============

DETECTION_PROMPT = """你是视频内容分类专家。下面给你 5 张代表帧 + 前 30 秒音轨转写，请判定这条视频的内容类型，输出严格 JSON：

{
  "content_type": "talking | visual | keyframe",
  "confidence": "高 | 中 | 低",
  "reason": "一句话说明判定依据"
}

判定规则：
- **talking**（口播主导）：画面以真人讲话/口播为主（说话头、教程口述、知识科普、播报）。视觉变化少，信息全在口播里。判别信号：真人脸长时间在画面 + 音轨密集说话。
- **visual**（视觉主导）：vlog / 表演 / 美食拍摄 / 转场剪辑 / 风景 / 运动。视觉变化丰富，口播少或无。判别信号：画面频繁切换 + BGM 主导 + 口播稀疏。
- **keyframe**（图文密集）：PPT 录屏 / 知识截图视频 / 思维导图 / 教程截屏 / 表格/代码展示。画面是稳定文字载体，时序信息少。判别信号：图上有大量文字 + 画面长时间静止 + 切换时换的是另一张图文。

只输出 JSON，不要任何额外文字。
"""

VISUAL_SEGMENT_SYSTEM = """你是一名小红书 / 抖音 / 快手 爆款视频拆解分析师。你的工作不是"描述视频内容"，
而是把视频片段拆解成可量化、可复用的钩子 + 结构变量。

严格按 JSON schema 输出，所有字段必填，不可"暂不可知"。"""

VISUAL_SEGMENT_USER = """这是一段视频片段（{seg_index}/{seg_total}，时长 ~{seg_dur}s，原视频时段 {start}s-{end}s）。

请按以下 JSON schema 拆解，输出严格 JSON（不要 markdown 代码块标记）：

{{
  "segment_index": {seg_index},
  "time_range": "{start}s-{end}s",
  "visual_hooks": {{
    "first_3s_hook_type": "提问 / 反差 / 数字 / 承诺 / 悬念前置 / 身份锁定 / 无明显钩子",
    "first_3s_description": "前 3 秒画面+口播+大字 一句话描述",
    "shot_changes_per_10s": "估算每 10 秒切镜次数（数字）",
    "camera_movement": "固定 / 推拉 / 摇移 / 跟拍 / 手持抖动 / 快剪混合",
    "on_screen_text": "屏幕大字 OCR（按时间顺序逗号分隔），无则空字符串",
    "human_presence": "真人出镜 / 真人手 / 纯产品 / 纯截图 / 屏幕录制 / 无人",
    "edit_rhythm": "慢节奏（>3s/镜）/ 中节奏（1-3s/镜）/ 快节奏（<1s/镜）"
  }},
  "structure_signals": {{
    "matched_skeleton": "A 场景+冲突+解决 / B 人设+故事+产品 / C 数据对比+结论 / 其他",
    "info_density": "高 / 中 / 低",
    "key_moments": [
      {{"t": "片段内秒数", "what": "发生了什么（钩子/转折/产品出现/CTA）"}}
    ]
  }},
  "audio_visual_match": {{
    "口播_vs_画面": "强同步（口播即画面）/ 弱同步（口播+B-roll）/ 不匹配",
    "bgm_presence": "有 BGM / 无 / 仅环境音",
    "emotion_arc": "平稳 / 起伏 / 反转"
  }},
  "interaction_triggers_visual": {{
    "comment_bait_visual": "画面里是否埋了评论钩子（开放问字幕 / 选边站 / 求资源），原文/无",
    "follow_bait_visual": "画面里是否埋了关注钩子（系列承诺 / 下篇预告），原文/无",
    "save_bait_visual": "是否出现清单/模板/表格等收藏诱饵，原文/无"
  }},
  "weakness": "这一段在「留存率」维度的明显短板（如：第 5 秒平庸 / 中段拖沓 / 无强 CTA）"
}}

只输出 JSON，不要任何额外文字。"""

TALKING_TRANSCRIPT_SYSTEM = """你是一名口播类视频拆解分析师。给你一段视频的全文 ASR 转写稿（口播文字），
请按 SKILL.md §5 的"评分术语"维度，把口播稿拆解成可量化的钩子结构。

严格按 JSON schema 输出，所有字段必填。"""

TALKING_TRANSCRIPT_USER = """这是视频的全文 ASR 转写稿（口播文字）。视频总时长 {dur}s。

转写稿如下：
\"\"\"
{transcript}
\"\"\"

请按以下 JSON schema 拆解，输出严格 JSON（不要 markdown 代码块标记）：

{{
  "opening_hook": {{
    "first_sentence": "首句口播原文",
    "matched_hook_id": "0-7（0=无；1 提问 / 2 反差 / 3 数字 / 4 承诺 / 5 悬念前置 / 6 身份锁定 / 7 利他诱饵 — 见 SKILL.md §5.4）",
    "audience_lock": "首句是否锁定了人群？锁定的是？无则空字符串",
    "weakness": "首句口播的短板（如：自我介绍废话 / 无利益承诺 / 无人群锚定）"
  }},
  "info_density": {{
    "level": "高 / 中 / 低",
    "key_points_count": "估算转述的有效信息点数量（数字）",
    "filler_ratio": "废话占比 0.0-1.0（自我介绍 / 客套 / 重复）"
  }},
  "structure": {{
    "matched_skeleton": "A 场景+冲突+解决 / B 人设+故事+产品 / C 数据对比+结论 / 其他",
    "section_breakdown": [
      {{"section": "开头/中段/结尾", "what": "这一段在干什么"}}
    ]
  }},
  "cta": {{
    "ending_cta": "结尾 CTA 原文（关注/评论/收藏/下一集），无则空字符串",
    "comment_bait": "口播里有没有埋评论钩子？原文/无",
    "follow_bait": "口播里有没有埋关注钩子？原文/无",
    "save_bait": "口播里有没有提到资源/清单/模板诱导收藏？原文/无"
  }},
  "title_formula_hint": {{
    "matched_formula_id": "口播主题对应 SKILL.md §5.2 第几号标题公式（1-10），命中不上写 0",
    "reason": "一句话说明"
  }},
  "weakness": "这条口播在「完播 + 互动」维度的最大短板（一句话）"
}}

只输出 JSON，不要任何额外文字。"""

KEYFRAME_SYSTEM = """你是一名图文密集型短视频/教程视频的关键帧拆解分析师。每张关键帧通常是一张知识截图/PPT/思维导图。
你的工作是 OCR + 提炼可复用知识点 + 评估视觉呈现。

严格按 JSON schema 输出，所有字段必填。"""

KEYFRAME_USER = """这是关键帧 {idx}/{total}（位于视频 {t}s）。请按以下 JSON schema 拆解：

{{
  "frame_index": {idx},
  "timestamp": {t},
  "ocr_full_text": "这张图上所有可读的文字（完整 OCR，原文返回，保留换行用 \\n）",
  "main_title": "这张图的主标题/最大字（无则空字符串）",
  "knowledge_point": "这张图传达的核心知识点 / 信息（一句话总结）",
  "visual_template": "纯文字 PPT / 思维导图 / 表格 / 代码截图 / 图文混排 / 其他",
  "info_density": "高 / 中 / 低",
  "design_quality": {{
    "readable": "易读 / 一般 / 难读",
    "hierarchy": "层级清晰 / 平铺 / 混乱",
    "color_use": "高对比 / 同色系弱 / 杂乱"
  }},
  "is_screenshot_of_app": "是 / 否（是不是某 APP 界面截图，比如微信/小红书/抖音）",
  "weakness": "这张关键帧在「让观众停留+收藏」维度的短板（一句话）"
}}

只输出 JSON，不要任何额外文字。"""


# ============ 工具函数 ============

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ffprobe_duration(path: str) -> float:
    r = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr}")
    return float(r.stdout.strip())


def b64_file(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def b64_image(path: str) -> str:
    return b64_file(path)


def gemini_chat(messages: list, max_tokens: int = 2500, temperature: float = 0.2) -> dict:
    """统一的 Gemini 调用 — OpenAI 兼容协议。返回解析后的 JSON dict（或带 error 的 dict）。"""
    api_key = os.environ["VIDEO_ANALYSIS_API_KEY"]
    base_url = os.environ.get("VIDEO_ANALYSIS_BASE_URL", "https://daydream88.fun/v1")
    model = os.environ.get("VIDEO_ANALYSIS_MODEL_NAME", "gemini-3.1-pro-preview")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        r = requests.post(f"{base_url}/chat/completions", headers=headers,
                          json=payload, timeout=300)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        return json.loads(content)
    except requests.HTTPError as e:
        return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except json.JSONDecodeError:
        return {"error": "non-JSON", "raw": content[:500]}
    except Exception as e:
        return {"error": str(e)}


# ============ 视频切段（visual / talking） ============

def cut_segments(video_path: str, workdir: Path, total_dur: float, seg_seconds: int) -> list:
    segments = []
    n = max(1, int((total_dur + seg_seconds - 1) // seg_seconds))
    for i in range(n):
        start = i * seg_seconds
        dur = min(seg_seconds, total_dur - start)
        if dur <= 0:
            break
        out = workdir / f"seg_{i:03d}.mp4"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(start), "-t", str(dur),
            "-i", video_path,
            "-c:v", "libx264", "-crf", "28", "-preset", "fast",
            "-vf", "scale=720:-2",
            "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart",
            str(out),
        ]
        r = run(cmd)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"ffmpeg seg {i} failed: {r.stderr[:300]}")
        size = out.stat().st_size
        if size > VIDEO_SEGMENT_MAX_BYTES:
            out2 = workdir / f"seg_{i:03d}_lq.mp4"
            r2 = run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(out),
                "-c:v", "libx264", "-crf", "32", "-preset", "fast",
                "-vf", "scale=540:-2", "-r", "20",
                "-c:a", "aac", "-b:a", "64k",
                str(out2),
            ])
            if r2.returncode == 0 and out2.exists():
                out.unlink()
                out = out2
                size = out.stat().st_size
        segments.append({
            "index": i, "start": start, "end": start + dur,
            "duration": dur, "path": str(out), "size": size,
        })
    return segments


def call_visual_segment(seg: dict, total_segs: int) -> dict:
    b64 = b64_file(seg["path"])
    user_prompt = VISUAL_SEGMENT_USER.format(
        seg_index=seg["index"], seg_total=total_segs,
        seg_dur=int(seg["duration"]), start=int(seg["start"]), end=int(seg["end"]),
    )
    result = gemini_chat([
        {"role": "system", "content": VISUAL_SEGMENT_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": user_prompt},
            {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}},
        ]},
    ])
    if "error" in result:
        result["segment_index"] = seg["index"]
    return result


# ============ 关键帧抽取（keyframe mode） ============

def extract_keyframes(video_path: str, workdir: Path, total_dur: float) -> list:
    """ffmpeg scene change detection 抽关键帧。超过上限取前 N 张。"""
    cap = keyframe_cap(total_dur)
    raw_dir = workdir / "keyframes_raw"
    raw_dir.mkdir(exist_ok=True)

    # showinfo 输出 frame timestamp 到 stderr，scene>threshold 的帧才会被 select
    cmd = [
        "ffmpeg", "-y", "-loglevel", "info",
        "-i", video_path,
        "-vf", f"select='gt(scene,{KEYFRAME_SCENE_THRESHOLD})',showinfo,scale=960:-2",
        "-fps_mode", "vfr",
        "-frames:v", str(cap * 2),  # 抽多一点，下面再筛
        str(raw_dir / "kf_%03d.jpg"),
    ]
    r = run(cmd)

    # 从 stderr 解析 pts_time
    pts_times = []
    for line in r.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            pts_times.append(float(m.group(1)))

    files = sorted(raw_dir.glob("kf_*.jpg"))

    # 如果场景检测没抽出足够帧，降级为均匀抽帧（适用于纯静态长视频）
    if len(files) < min(5, cap):
        for f in files:
            f.unlink()
        files = []
        pts_times = []
        n = min(cap, max(5, int(total_dur // 30)))  # 至少 5 张
        for i in range(n):
            t = (i + 0.5) * (total_dur / n)
            out = raw_dir / f"kf_{i:03d}.jpg"
            run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(t), "-i", video_path,
                "-vf", "scale=960:-2",
                "-frames:v", "1",
                str(out),
            ])
            if out.exists():
                files.append(out)
                pts_times.append(t)

    # 截到 cap 上限
    files = files[:cap]
    pts_times = pts_times[:cap] if len(pts_times) >= len(files) else (
        pts_times + [0.0] * (len(files) - len(pts_times))
    )

    keyframes = []
    for i, (f, t) in enumerate(zip(files, pts_times)):
        keyframes.append({"index": i, "timestamp": round(t, 2), "path": str(f)})
    return keyframes


def call_keyframe_analysis(kf: dict, total: int) -> dict:
    b64 = b64_image(kf["path"])
    user_prompt = KEYFRAME_USER.format(idx=kf["index"], total=total, t=kf["timestamp"])
    result = gemini_chat([
        {"role": "system", "content": KEYFRAME_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]},
    ], max_tokens=2000)
    if "error" in result:
        result["frame_index"] = kf["index"]
        result["timestamp"] = kf["timestamp"]
    return result


# ============ ASR 音轨 ============

def extract_audio(video_path: str, workdir: Path, max_seconds: float = None) -> Path:
    out = workdir / "audio.mp3"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path, "-vn",
    ]
    if max_seconds is not None:
        cmd += ["-t", str(max_seconds)]
    cmd += [
        "-acodec", "libmp3lame", "-b:a", "96k", "-ar", "16000", "-ac", "1",
        str(out),
    ]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {r.stderr[:300]}")
    return out


def split_audio_if_needed(audio_path: Path, workdir: Path, total_dur: float) -> list:
    if audio_path.stat().st_size <= AUDIO_MAX_BYTES:
        return [{"index": 0, "start": 0, "end": total_dur, "path": str(audio_path)}]
    chunks = []
    n = max(1, int((total_dur + AUDIO_CHUNK_SECONDS - 1) // AUDIO_CHUNK_SECONDS))
    for i in range(n):
        start = i * AUDIO_CHUNK_SECONDS
        dur = min(AUDIO_CHUNK_SECONDS, total_dur - start)
        if dur <= 0:
            break
        out = workdir / f"audio_{i:03d}.mp3"
        r = run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(start), "-t", str(dur), "-i", str(audio_path),
            "-c", "copy", str(out),
        ])
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg audio split {i} failed: {r.stderr[:300]}")
        chunks.append({"index": i, "start": start, "end": start + dur, "path": str(out)})
    return chunks


def call_sensevoice(audio_chunks: list, required: bool = False) -> dict:
    api_key = os.environ.get("AUDIO_TRANSCRIPTION_API_KEY")
    if not api_key:
        if required:
            raise RuntimeError(
                "talking 模式必须设 AUDIO_TRANSCRIPTION_API_KEY（口播主导视频没 ASR=没法分析）"
            )
        return {"skipped": True, "reason": "AUDIO_TRANSCRIPTION_API_KEY not set"}
    base_url = os.environ.get("AUDIO_TRANSCRIPTION_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.environ.get("AUDIO_TRANSCRIPTION_MODEL", "FunAudioLLM/SenseVoiceSmall")

    full_text_parts = []
    chunk_results = []
    for c in audio_chunks:
        try:
            with open(c["path"], "rb") as f:
                files = {"file": (Path(c["path"]).name, f, "audio/mpeg")}
                data = {"model": model}
                headers = {"Authorization": f"Bearer {api_key}"}
                r = requests.post(
                    f"{base_url}/audio/transcriptions",
                    headers=headers, files=files, data=data, timeout=600,
                )
                r.raise_for_status()
                resp = r.json()
                text = resp.get("text", "").strip()
                full_text_parts.append(text)
                chunk_results.append({
                    "index": c["index"], "start": c["start"], "end": c["end"],
                    "text": text,
                })
        except requests.HTTPError as e:
            chunk_results.append({
                "index": c["index"],
                "error": f"HTTP {e.response.status_code}",
                "detail": e.response.text[:500],
            })
        except Exception as e:
            chunk_results.append({"index": c["index"], "error": str(e)})

    return {"full_text": "\n".join(full_text_parts), "chunks": chunk_results}


# ============ Auto detection ============

def detect_content_type(video_path: str, workdir: Path, total_dur: float) -> dict:
    """抽 5 张代表帧 + 前 30s 音轨喂 Gemini，判定 talking / visual / keyframe。"""
    # 5 张代表帧（先试 scene change，不够均匀）
    det_dir = workdir / "detection_frames"
    det_dir.mkdir(exist_ok=True)
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-vf", "select='gt(scene,0.4)',scale=480:-2",
        "-fps_mode", "vfr",
        "-frames:v", str(DETECTION_FRAME_COUNT),
        str(det_dir / "det_%02d.jpg"),
    ])
    files = sorted(det_dir.glob("det_*.jpg"))
    if len(files) < DETECTION_FRAME_COUNT:
        # 均匀抽满 5 张
        for f in files:
            f.unlink()
        files = []
        for i in range(DETECTION_FRAME_COUNT):
            t = (i + 0.5) * (total_dur / DETECTION_FRAME_COUNT)
            out = det_dir / f"det_{i:02d}.jpg"
            run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(t), "-i", video_path,
                "-vf", "scale=480:-2", "-frames:v", "1",
                str(out),
            ])
            if out.exists():
                files.append(out)

    # 前 30s 音轨转写（如果 ASR key 有的话；没有就跳过）
    transcript_snippet = ""
    api_key = os.environ.get("AUDIO_TRANSCRIPTION_API_KEY")
    if api_key:
        try:
            audio_path = extract_audio(video_path, workdir,
                                        max_seconds=min(DETECTION_AUDIO_SECONDS, total_dur))
            asr = call_sensevoice([{"index": 0, "start": 0,
                                     "end": min(DETECTION_AUDIO_SECONDS, total_dur),
                                     "path": str(audio_path)}])
            transcript_snippet = asr.get("full_text", "")[:500]
        except Exception:
            transcript_snippet = ""

    # 拼 prompt
    user_content = [
        {"type": "text",
         "text": DETECTION_PROMPT + f"\n\n前 30 秒口播转写：\n\"\"\"\n{transcript_snippet or '（无 ASR 或音轨为空）'}\n\"\"\"\n\n下面是 5 张代表帧："},
    ]
    for f in files:
        b64 = b64_image(str(f))
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    result = gemini_chat([
        {"role": "system", "content": "你是视频内容分类专家。"},
        {"role": "user", "content": user_content},
    ], max_tokens=400, temperature=0.1)

    # fallback：error 时默认 visual
    if "error" in result or "content_type" not in result:
        return {
            "content_type": "visual",
            "confidence": "低",
            "reason": "auto detection 失败，降级为 visual",
            "detection_error": result.get("error") if "error" in result else "missing field",
        }
    return result


# ============ 三种 mode 的主流程 ============

def run_visual_mode(video_path: str, workdir: Path, total_dur: float) -> dict:
    segments = cut_segments(video_path, workdir, total_dur, SEGMENT_SECONDS_VISUAL)
    visual_results = [call_visual_segment(s, len(segments)) for s in segments]

    # ASR 可选
    transcript = {"skipped": True, "reason": "visual mode skips ASR by default"}
    audio_chunks = []
    if os.environ.get("AUDIO_TRANSCRIPTION_API_KEY"):
        try:
            audio_path = extract_audio(video_path, workdir)
            audio_chunks = split_audio_if_needed(audio_path, workdir, total_dur)
            transcript = call_sensevoice(audio_chunks)
        except Exception as e:
            transcript = {"error": str(e)}

    key_moments = []
    for v in visual_results:
        seg_start = next((s["start"] for s in segments
                          if s["index"] == v.get("segment_index")), 0)
        for km in (v.get("structure_signals") or {}).get("key_moments", []) or []:
            try:
                t_in_seg = float(km.get("t", 0))
            except (TypeError, ValueError):
                continue
            key_moments.append({
                "absolute_t": seg_start + t_in_seg,
                "segment": v.get("segment_index"),
                "what": km.get("what", ""),
            })
    key_moments.sort(key=lambda x: x["absolute_t"])

    return {
        "mode_used": "visual",
        "segment_count": len(segments),
        "segments": [{"index": s["index"], "start": s["start"], "end": s["end"]}
                     for s in segments],
        "visual_analysis": visual_results,
        "transcript": transcript,
        "key_moments": key_moments,
    }


def run_talking_mode(video_path: str, workdir: Path, total_dur: float) -> dict:
    # ASR 必须跑通
    audio_path = extract_audio(video_path, workdir)
    audio_chunks = split_audio_if_needed(audio_path, workdir, total_dur)
    transcript = call_sensevoice(audio_chunks, required=True)
    if transcript.get("chunks") and all("error" in c for c in transcript["chunks"]):
        raise RuntimeError(f"talking mode: ASR failed for all chunks: {transcript}")

    full_text = transcript.get("full_text", "")
    if not full_text.strip():
        raise RuntimeError("talking mode: ASR returned empty transcript")

    # 把转写稿喂 Gemini 做口播分析
    user_prompt = TALKING_TRANSCRIPT_USER.format(
        dur=int(total_dur),
        transcript=full_text[:8000],  # 控制 token
    )
    transcript_analysis = gemini_chat([
        {"role": "system", "content": TALKING_TRANSCRIPT_SYSTEM},
        {"role": "user", "content": user_prompt},
    ], max_tokens=2500)

    # 视觉做轻量分段（180s 一段）— 验证人设/出镜/封面一致性
    segments = cut_segments(video_path, workdir, total_dur, SEGMENT_SECONDS_TALKING)
    visual_results = [call_visual_segment(s, len(segments)) for s in segments]

    return {
        "mode_used": "talking",
        "transcript": transcript,
        "transcript_analysis": transcript_analysis,
        "segment_count": len(segments),
        "segments": [{"index": s["index"], "start": s["start"], "end": s["end"]}
                     for s in segments],
        "visual_analysis": visual_results,
    }


def run_keyframe_mode(video_path: str, workdir: Path, total_dur: float) -> dict:
    keyframes = extract_keyframes(video_path, workdir, total_dur)
    if not keyframes:
        raise RuntimeError("keyframe mode: no keyframes extracted (check ffmpeg + scene change)")

    keyframe_results = [call_keyframe_analysis(kf, len(keyframes)) for kf in keyframes]

    # ASR 仅作辅助
    transcript = {"skipped": True, "reason": "keyframe mode treats ASR as auxiliary"}
    if os.environ.get("AUDIO_TRANSCRIPTION_API_KEY"):
        try:
            audio_path = extract_audio(video_path, workdir)
            audio_chunks = split_audio_if_needed(audio_path, workdir, total_dur)
            transcript = call_sensevoice(audio_chunks)
        except Exception as e:
            transcript = {"error": str(e)}

    return {
        "mode_used": "keyframe",
        "keyframe_count": len(keyframes),
        "keyframe_cap": keyframe_cap(total_dur),
        "keyframes": [{"index": kf["index"], "timestamp": kf["timestamp"]} for kf in keyframes],
        "keyframe_analysis": keyframe_results,
        "transcript": transcript,
    }


# ============ 入口 ============

def analyze(video_path: str, mode: str = "auto") -> dict:
    if not Path(video_path).exists():
        return {"error": f"video not found: {video_path}"}
    if not os.environ.get("VIDEO_ANALYSIS_API_KEY"):
        return {"error": "VIDEO_ANALYSIS_API_KEY not set"}
    for tool in ("ffmpeg", "ffprobe"):
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            return {"error": f"{tool} not installed (sudo apt install ffmpeg)"}

    valid_modes = {"auto", "talking", "visual", "keyframe"}
    if mode not in valid_modes:
        return {"error": f"invalid mode: {mode}, must be one of {valid_modes}"}

    with tempfile.TemporaryDirectory(prefix="account_diag_") as tmp:
        workdir = Path(tmp)
        try:
            duration = ffprobe_duration(video_path)

            mode_detection = None
            actual_mode = mode
            if mode == "auto":
                mode_detection = detect_content_type(video_path, workdir, duration)
                actual_mode = mode_detection["content_type"]

            if actual_mode == "talking":
                result = run_talking_mode(video_path, workdir, duration)
            elif actual_mode == "keyframe":
                result = run_keyframe_mode(video_path, workdir, duration)
            else:  # visual or fallback
                result = run_visual_mode(video_path, workdir, duration)

            # 统一外壳
            output = {
                "video_path": video_path,
                "duration_seconds": duration,
                "mode_requested": mode,
                "mode_used": result["mode_used"],
            }
            if mode_detection is not None:
                output["mode_detection"] = mode_detection
            output.update({k: v for k, v in result.items() if k != "mode_used"})
            return output
        except Exception as e:
            return {"error": str(e), "mode_requested": mode}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video_path", help="本地视频路径")
    p.add_argument("--mode", default="auto",
                   choices=["auto", "talking", "visual", "keyframe"],
                   help="分析路径：auto 自动判定（默认）/ talking 口播主导 / "
                        "visual 视觉主导 / keyframe 图文密集")
    args = p.parse_args()
    print(json.dumps(analyze(args.video_path, args.mode), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
