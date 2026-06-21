#!/usr/bin/env python3
"""
social-account-doctor: analyze_image.py

输入：1 张或多张本地图片路径（小红书 / 抖音 / 快手 封面 / 首帧 / 截图）
输出：JSON — 封面 5 变量 + 模板归类 + 大字 OCR + 钩子识别 + 标题公式提示
      单张 → 单个 JSON 对象；多张 → JSON 数组

支持 --concurrency N 控制并发数（默认 1），避免 API 限流。
支持 --timeout N 或 VIDEO_ANALYSIS_TIMEOUT_SECONDS 控制单次模型调用读超时（默认 600 秒）。
非 JPEG 图片会尽量归一化为 JPEG 再发给 OpenAI 兼容多模态接口。

调用 Gemini 3.1 Pro（OpenAI 兼容协议，base_url 走环境变量）。

术语对齐（自包含，参考 SKILL.md §"评分术语速查"）：
  五种封面模板：A 大字报 / B 对比 / C 真人出镜 / D 实物展示 / E 表格截图
  10 个标题公式：见 SKILL.md，模型只需返回编号
"""

import argparse
import base64
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print(json.dumps({"error": "missing dependency: pip install requests"}, ensure_ascii=False))
    sys.exit(1)


SYSTEM_PROMPT = """你是一名小红书 / 抖音 / 快手 爆款拆解分析师。你的工作不是"描述图片"，而是把封面图拆解成可量化、可复用的模板变量。

严格按 JSON schema 输出，所有字段都要填，不能"暂不可知"。
"""

DEFAULT_ANALYSIS_TIMEOUT_SECONDS = 600

USER_PROMPT = """请按以下 JSON schema 拆解这张封面图，输出严格 JSON（不要任何 markdown 代码块标记）：

{
  "cover_variables": {
    "ratio": "3:4 / 1:1 / 16:9 / 9:16 / 其他",
    "big_text": "封面上最大的字（OCR 提取，原文返回，无则空字符串）",
    "big_text_ratio": "大字占封面面积比例（0.0-1.0 估算）",
    "human_presence": "真人脸 / 真人手 / 真人全身 / 纯产品 / 纯截图 / 无人",
    "color_contrast": "暖底冷字 / 冷底暖字 / 高饱和+低饱和 / 黑白对比 / 同色系（弱）",
    "info_density": "高（人群+利益一眼可见） / 中（一个明确利益点） / 低（仅展示无利益）"
  },
  "template_classification": {
    "matched": "A / B / C / D / E",
    "name": "A 大字报型 / B 对比型 / C 真人出镜型 / D 实物展示型 / E 表格截图型",
    "confidence": "高 / 中 / 低",
    "reason": "一句话说明为什么命中这个模板"
  },
  "hook_detection": {
    "audience_lock": "封面是否锁定了目标人群？锁定的人群是？（无则空字符串）",
    "benefit_promise": "封面承诺的具体利益点（数字/省钱/省时/避坑/抄作业），无则空字符串",
    "curiosity_gap": "是否制造了好奇悬念？怎么制造的？（无则空字符串）"
  },
  "title_formula_hint": {
    "matched_formula_id": "封面文案像第几号标题公式（1 数字+人群+效果 / 2 反认知钩子 / 3 极端体验 / 4 怕错避坑 / 5 答案前置 / 6 身份共鸣 / 7 升维加码 / 8 资源诱饵 / 9 时间锚定 / 10 对比反差）；命中不上写 0",
    "reason": "一句话说明"
  },
  "weakness": "这个封面在「点击率」维度有什么明显短板？（如：大字不够大 / 颜色对比弱 / 无人群锚定 / 信息密度低）"
}

只输出 JSON，不要任何额外文字。
"""


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def detect_mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def prepare_image_payload(path: str) -> tuple[str, str]:
    raw = Path(path).read_bytes()
    mime = detect_mime(path)
    normalize = os.environ.get("VIDEO_ANALYSIS_NORMALIZE_IMAGES", "1").lower() not in {"0", "false", "no"}
    if not normalize or mime == "image/jpeg":
        return base64.b64encode(raw).decode("utf-8"), mime

    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
                background = Image.new("RGBA", img.size, (255, 255, 255, 255))
                background.alpha_composite(img)
                img = background.convert("RGB")
            else:
                img = img.convert("RGB")

            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            img.thumbnail((1800, 1800), resampling)
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=92, optimize=True)
    except Exception as e:
        _progress(f"image normalization skipped: {type(e).__name__}: {e}")
        return base64.b64encode(raw).decode("utf-8"), mime

    _progress(f"normalized {mime} to image/jpeg for model compatibility")
    return base64.b64encode(out.getvalue()).decode("utf-8"), "image/jpeg"


def _progress(msg: str) -> None:
    print(f"[analyze_image] {msg}", file=sys.stderr, flush=True)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def analysis_timeout_seconds(override: Optional[int] = None) -> int:
    if override is not None:
        return max(1, override)
    return _env_int("VIDEO_ANALYSIS_TIMEOUT_SECONDS", DEFAULT_ANALYSIS_TIMEOUT_SECONDS)


def chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _call_once(
    api_key: str,
    base_url: str,
    model: str,
    b64: str,
    mime: str,
    max_tokens: int,
    timeout_seconds: int,
) -> dict:
    _progress(f"calling {model} with max_tokens={max_tokens}, timeout={timeout_seconds}s ...")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(
            chat_completions_url(base_url),
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        content = (choice.get("message", {}).get("content") or "").strip()
        finish_reason = choice.get("finish_reason", "")
        _progress(f"done, finish_reason={finish_reason}, content_len={len(content)}")
        return {"ok": True, "content": content, "finish_reason": finish_reason}
    except requests.HTTPError as e:
        return {
            "ok": False,
            "error": f"HTTP {e.response.status_code}",
            "detail": e.response.text[:500],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _parse_json(content: str) -> dict:
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    return json.loads(content)


def analyze(image_path: str, timeout_seconds: Optional[int] = None) -> dict:
    api_key = os.environ.get("VIDEO_ANALYSIS_API_KEY")
    base_url = os.environ.get("VIDEO_ANALYSIS_BASE_URL", "https://daydream88.fun/v1")
    model = os.environ.get("VIDEO_ANALYSIS_MODEL_NAME", "gemini-3.1-pro-preview")
    timeout_seconds = analysis_timeout_seconds(timeout_seconds)

    if not api_key:
        return {"error": "VIDEO_ANALYSIS_API_KEY not set in env"}

    if not Path(image_path).exists():
        return {"error": f"image not found: {image_path}"}

    b64, mime = prepare_image_payload(image_path)
    budgets = [8000, 16000]
    last_content = ""
    last_finish = ""
    last_error = None

    for max_tokens in budgets:
        resp = _call_once(api_key, base_url, model, b64, mime, max_tokens, timeout_seconds)
        if not resp["ok"]:
            last_error = {"error": resp.get("error"), "detail": resp.get("detail")}
            break

        last_content = resp["content"]
        last_finish = resp["finish_reason"]
        if last_finish == "length":
            continue

        try:
            return _parse_json(last_content)
        except json.JSONDecodeError:
            continue

    if last_error:
        return last_error
    return {
        "error": "model output could not be parsed as JSON",
        "finish_reason": last_finish,
        "raw": last_content[:1500],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image_paths", nargs="+", help="本地图片路径（支持多张）")
    p.add_argument("--concurrency", type=int, default=1,
                   help="并发数（默认 1，确认额度充足时再手动调高）")
    p.add_argument("--timeout", type=int, default=None,
                   help="单次模型调用读超时秒数")
    args = p.parse_args()

    paths = args.image_paths
    if len(paths) == 1:
        result = analyze(paths[0], args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    concurrency = max(1, args.concurrency)
    _progress(f"batch mode: {len(paths)} images, concurrency={concurrency}")
    results = [None] * len(paths)

    def _run(idx: int, path: str):
        _progress(f"[{idx + 1}/{len(paths)}] analyzing {Path(path).name} ...")
        start = time.time()
        result = analyze(path, args.timeout)
        _progress(f"[{idx + 1}/{len(paths)}] {Path(path).name} done ({time.time() - start:.1f}s)")
        return idx, path, result

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_run, i, path) for i, path in enumerate(paths)]
        for future in as_completed(futures):
            idx, path, result = future.result()
            results[idx] = {"file": Path(path).name, **result}

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
