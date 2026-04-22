#!/usr/bin/env python3
"""
social-account-doctor: analyze_image.py

输入：本地图片路径（小红书 / 抖音 / 快手 封面 / 首帧 / 截图）
输出：JSON — 封面 5 变量 + 模板归类 + 大字 OCR + 钩子识别 + 标题公式提示

调用 Gemini 3.1 Pro（OpenAI 兼容协议，base_url 走环境变量）。

术语对齐（自包含，参考 SKILL.md §"评分术语速查"）：
  五种封面模板：A 大字报 / B 对比 / C 真人出镜 / D 实物展示 / E 表格截图
  10 个标题公式：见 SKILL.md，模型只需返回编号
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print(json.dumps({"error": "missing dependency: pip install requests"}, ensure_ascii=False))
    sys.exit(1)


SYSTEM_PROMPT = """你是一名小红书 / 抖音 / 快手 爆款拆解分析师。你的工作不是"描述图片"，而是把封面图拆解成可量化、可复用的模板变量。

严格按 JSON schema 输出，所有字段都要填，不能"暂不可知"。
"""

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


def analyze(image_path: str) -> dict:
    api_key = os.environ.get("VIDEO_ANALYSIS_API_KEY")
    base_url = os.environ.get("VIDEO_ANALYSIS_BASE_URL", "https://daydream88.fun/v1")
    model = os.environ.get("VIDEO_ANALYSIS_MODEL_NAME", "gemini-3.1-pro-preview")

    if not api_key:
        return {"error": "VIDEO_ANALYSIS_API_KEY not set in env"}

    if not Path(image_path).exists():
        return {"error": f"image not found: {image_path}"}

    b64 = encode_image(image_path)
    mime = detect_mime(image_path)

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
        "max_tokens": 2000,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        return json.loads(content)
    except requests.HTTPError as e:
        return {
            "error": f"HTTP {e.response.status_code}",
            "detail": e.response.text[:500],
        }
    except json.JSONDecodeError:
        return {"error": "model returned non-JSON", "raw": content[:1000]}
    except Exception as e:
        return {"error": str(e)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image_path", help="本地图片路径")
    args = p.parse_args()

    result = analyze(args.image_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
