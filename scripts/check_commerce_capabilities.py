#!/usr/bin/env python3
"""Check whether the live TikHub catalog can support the Douyin commerce workflow.

Usage:
    check_commerce_capabilities.py [--offline]

Online mode reads the live TikHub tool catalog. Offline mode reads the bundled
catalog and is useful only for installation diagnostics; it is not proof that a
tool still exists remotely.
"""

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TIKHUB_LIB = REPO_ROOT / "tikhub" / "lib"
CATALOG = REPO_ROOT / "tikhub" / "references" / "tools-douyin.json"

REQUIRED_TOOLS = {
    "product_detail": "douyin_web_fetch_product_detail",
    "sku": "douyin_web_fetch_product_sku_list",
    "reviews": "douyin_web_fetch_product_review_list",
    "video_search": "douyin_search_fetch_video_search_v2",
    "video_detail": "douyin_app_v3_fetch_one_video_v3",
}
OPTIONAL_TOOLS = {
    "coupon": "douyin_web_fetch_product_coupon",
    "review_score": "douyin_web_fetch_product_review_score",
    "video_statistics": "douyin_app_v3_fetch_video_statistics",
}


def assess(tool_names: set[str], source: str) -> dict:
    required = {key: name in tool_names for key, name in REQUIRED_TOOLS.items()}
    optional = {key: name in tool_names for key, name in OPTIONAL_TOOLS.items()}
    missing = [REQUIRED_TOOLS[key] for key, available in required.items() if not available]
    product_ready = all(required[key] for key in ("product_detail", "sku", "reviews"))
    workflow_ready = product_ready and all(required.values())
    return {
        "platform": "douyin",
        "source": source,
        "status": "ready" if workflow_ready else "degraded",
        "product_fact_ready": product_ready,
        "full_workflow_ready": workflow_ready,
        "required": required,
        "optional": optional,
        "missing_required_tools": missing,
        "fallback": None if product_ready else "要求用户提供商品详情/SKU/资质截图，构建手动事实卡；禁止猜测商品事实。",
    }


def load_offline_names() -> set[str]:
    with open(CATALOG, encoding="utf-8") as f:
        return {tool.get("name", "") for tool in json.load(f)}


def load_live_names() -> set[str]:
    sys.path.insert(0, str(TIKHUB_LIB))
    from tikhub_client import TikhubClient  # pylint: disable=import-outside-toplevel

    return {tool.get("name", "") for tool in TikhubClient("douyin").list_tools()}


def main() -> None:
    offline = "--offline" in sys.argv[1:]
    try:
        names = load_offline_names() if offline else load_live_names()
        result = assess(names, "bundled-cache" if offline else "live-tikhub")
    except Exception as e:  # external service failures must become structured degradation
        result = {
            "platform": "douyin",
            "source": "live-tikhub",
            "status": "unavailable",
            "product_fact_ready": False,
            "full_workflow_ready": False,
            "error": str(e),
            "fallback": "要求用户提供商品详情/SKU/资质截图，构建手动事实卡；禁止猜测商品事实。",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "ready":
        sys.exit(2)


if __name__ == "__main__":
    main()
