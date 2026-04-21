#!/usr/bin/env python3
"""
account-diagnostic: ocr_screenshot.py
笔记/账号后台截图 → Gemini 3.1 Pro OCR → 结构化 JSON。

输入:本地截图路径(.png / .jpg / .jpeg / .webp)
输出:
{
  "platform_guess": "xiaohongshu / douyin / kuaishou / unknown",
  "screenshot_type": "note_metrics / account_overview / unknown",
  "metrics": {
    "impressions": int|null,        # 曝光数
    "clicks": int|null,             # 点击数
    "ctr": float|null,              # 点击率(0-1 小数)
    "completion_5s": float|null,    # 5s 完播率(抖音核心)
    "completion_full": float|null,  # 整体完播率
    "likes": int|null,
    "favorites": int|null,
    "comments": int|null,
    "shares": int|null,
    "follows_gained": int|null,     # 新增关注(快手核心)
    "ces_score": float|null,        # 小红书 CES
    "engagement_rate": float|null,  # 互动率
    ...
  },
  "raw_text": "OCR 全文(便于 caller 二次校验)",
  "warnings": ["指标 X 提取置信度低,建议人工确认", ...]
}

环境变量:
- VIDEO_ANALYSIS_API_KEY
- VIDEO_ANALYSIS_BASE_URL  (默认 https://generativelanguage.googleapis.com)
- VIDEO_ANALYSIS_MODEL_NAME  (默认 gemini-3-pro-preview)
"""

import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests 未安装,请运行 pip install requests"}, ensure_ascii=False))
    sys.exit(2)


PROMPT = """你是自媒体账号数据分析专家。这是一张笔记/账号后台数据截图,请按以下要求提取信息并输出严格 JSON(不要 markdown 代码块,直接 JSON):

{
  "platform_guess": "xiaohongshu | douyin | kuaishou | unknown",
  "screenshot_type": "note_metrics | account_overview | unknown",
  "metrics": {
    "impressions": 曝光数(整数,无则 null),
    "clicks": 点击数(整数),
    "ctr": 点击率(小数 0-1,例如 8.5% 写 0.085),
    "completion_5s": 5秒完播率(小数 0-1,抖音核心指标),
    "completion_full": 整体完播率(小数 0-1),
    "likes": 点赞数(整数),
    "favorites": 收藏数(整数,小红书重点),
    "comments": 评论数(整数),
    "shares": 转发/分享数(整数),
    "follows_gained": 新增关注数(整数,快手核心),
    "ces_score": 小红书 CES 分(小数,无则 null),
    "engagement_rate": 互动率(小数 0-1)
  },
  "raw_text": "截图里所有可读的文字(完整 OCR,用于校验)",
  "warnings": ["告警1", "告警2"]
}

平台识别提示:
- 小红书:有"曝光""阅读量""收藏"用蓝色调,可能有 CES 分
- 抖音:有"5秒完播率""粉丝增量""推荐量",创作者中心是黑色或粉色调
- 快手:有"老铁""作品热度",绿色调

提取规则:
1. 万/k 单位要换算成整数(1.5万 → 15000,8.5k → 8500)
2. 百分比要转成小数(8.5% → 0.085)
3. 拿不准的字段宁可写 null,也不要瞎猜
4. 把所有看不清/可能糊的指标加到 warnings 列表
5. 如果根本不是数据截图(比如是聊天记录、代码、随便的图),platform_guess 写 "unknown",screenshot_type 写 "unknown"

只输出 JSON,不要任何其他文字。"""


def encode_image_to_base64(path: Path) -> tuple[str, str]:
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        mime = "image/png"
    data = path.read_bytes()
    return base64.b64encode(data).decode("utf-8"), mime


def call_gemini(image_b64: str, mime: str, api_key: str, base_url: str, model: str) -> str:
    """调 Gemini API,兼容 generativelanguage.googleapis.com 格式 + OpenAI 兼容格式"""

    if "generativelanguage" in base_url:
        # 原生 Gemini 格式
        url = f"{base_url.rstrip('/')}/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": PROMPT},
                    {"inline_data": {"mime_type": mime, "data": image_b64}},
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    else:
        # OpenAI 兼容格式(很多代理是这种)
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: ocr_screenshot.py <截图路径>"}, ensure_ascii=False))
        sys.exit(1)

    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        print(json.dumps({"error": f"file not found: {path}"}, ensure_ascii=False))
        sys.exit(2)

    api_key = os.environ.get("VIDEO_ANALYSIS_API_KEY")
    if not api_key:
        print(json.dumps({"error": "VIDEO_ANALYSIS_API_KEY not set"}, ensure_ascii=False))
        sys.exit(3)

    base_url = os.environ.get("VIDEO_ANALYSIS_BASE_URL", "https://generativelanguage.googleapis.com")
    model = os.environ.get("VIDEO_ANALYSIS_MODEL_NAME", "gemini-3-pro-preview")

    image_b64, mime = encode_image_to_base64(path)

    try:
        raw = call_gemini(image_b64, mime, api_key, base_url, model)
    except requests.HTTPError as e:
        print(json.dumps({
            "error": f"API call failed: {e}",
            "response_body": e.response.text[:500] if e.response is not None else None,
        }, ensure_ascii=False))
        sys.exit(4)
    except Exception as e:
        print(json.dumps({"error": f"unexpected error: {type(e).__name__}: {e}"}, ensure_ascii=False))
        sys.exit(5)

    # Gemini 偶尔会返回带 markdown 代码块的 JSON,先剥一下
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(json.dumps({
            "error": f"Gemini 返回的不是合法 JSON: {e}",
            "raw_response": raw[:1000],
        }, ensure_ascii=False))
        sys.exit(6)

    # 兜底:确保 warnings 字段存在
    parsed.setdefault("warnings", [])
    if parsed.get("platform_guess") == "unknown":
        parsed["warnings"].append("无法识别平台,建议让用户补充平台名称或提供笔记链接")

    print(json.dumps(parsed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
