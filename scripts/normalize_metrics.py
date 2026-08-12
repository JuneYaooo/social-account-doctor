#!/usr/bin/env python3
"""
social-account-doctor: normalize_metrics.py
跨平台指标归一化 — 将不同平台的互动数据统一到可比基线。

用途：
1. 输入原始指标 JSON → 按粉丝规模分桶 → 输出相对同类账号中位数的倍数
2. 标记异常增长（超过基线 N 倍的值）
3. 补充数据完整度标记

不直接调平台 API。caller 自己拿到原始数据后，把 JSON 喂给本脚本做归一化。

用法:
    normalize_metrics.py <input.json> [--platform douyin/kuaishou/xhs] [--baseline account_id]
    normalize_metrics.py --help

输入 JSON 格式:
    {
      "platform": "douyin",
      "videos": [
        {
          "video_id": "...",
          "account_id": "...",
          "follower_count": 5000,
          "metrics": {
            "views": 12000,
            "likes": 800,
            "comments": 45,
            "shares": 23,
            "product_clicks": 120,
            "gmv": 3500
          },
          "published_at": "2026-08-10T14:30:00"
        }
      ]
    }

输出 JSON 格式:
    {
      "platform": "douyin",
      "bucket": "1k-10k",
      "bucket_median": { "views": ..., "likes": ..., "engagement_rate": ... },
      "videos": [
        {
          "video_id": "...",
          "raw_metrics": { ... },
          "vs_baseline": { "views_multiple": 2.3, "engagement_multiple": 1.8 },
          "growth_flags": ["views_spike", "engagement_anomaly"],
          "data_completeness": "full"
        }
      ],
      "warnings": []
    }
"""

import json
import statistics
import sys
from datetime import datetime, timezone
from typing import Optional

BUCKETS = [
    (0, 1_000, "0-1k"),
    (1_000, 10_000, "1k-10k"),
    (10_000, 100_000, "10k-100k"),
    (100_000, 1_000_000, "100k-1M"),
    (1_000_000, float("inf"), "1M+"),
]


def bucket_name(follower_count: int) -> str:
    for lo, hi, name in BUCKETS:
        if lo <= follower_count < hi:
            return name
    return "unknown"


def compute_engagement_rate(v: dict) -> Optional[float]:
    m = v.get("metrics", {})
    views = m.get("views", 0)
    if views <= 0:
        return None
    interactions = m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0)
    return interactions / views


def compute_median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return statistics.median(values)


def normalize_video(video: dict, bucket_medians: dict) -> dict:
    m = video.get("metrics", {})
    views = m.get("views", 0)
    engagements = m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0)

    vs_baseline = {}

    median_views = bucket_medians.get("views")
    if median_views and median_views > 0 and views > 0:
        vs_baseline["views_multiple"] = round(views / median_views, 2)
    else:
        vs_baseline["views_multiple"] = None

    median_engagement = bucket_medians.get("engagement_rate")
    if median_engagement and median_engagement > 0:
        er = compute_engagement_rate(video)
        if er is not None:
            vs_baseline["engagement_multiple"] = round(er / median_engagement, 2)
        else:
            vs_baseline["engagement_multiple"] = None
    else:
        vs_baseline["engagement_multiple"] = None

    growth_flags = []
    views_mult = vs_baseline.get("views_multiple")
    eng_mult = vs_baseline.get("engagement_multiple")

    if views_mult is not None:
        if views_mult >= 5:
            growth_flags.append("views_spike_5x")
        elif views_mult >= 3:
            growth_flags.append("views_spike_3x")
        elif views_mult >= 2:
            growth_flags.append("views_above_baseline")

    if eng_mult is not None:
        if eng_mult >= 3:
            growth_flags.append("engagement_anomaly_high")
        elif eng_mult <= 0.3:
            growth_flags.append("engagement_anomaly_low")

    missing = []
    for field in ("views", "likes", "comments", "shares"):
        if field not in m or m[field] is None:
            missing.append(field)
    if not missing:
        completeness = "full"
    elif len(missing) <= 3:
        completeness = "partial"
    else:
        completeness = "missing"

    return {
        "video_id": video.get("video_id", ""),
        "account_id": video.get("account_id", ""),
        "follower_count": video.get("follower_count", 0),
        "raw_metrics": m,
        "vs_baseline": vs_baseline,
        "growth_flags": growth_flags,
        "data_completeness": completeness,
    }


def load_input(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "videos" not in data:
        raise ValueError("input JSON must have a 'videos' key")
    return data


def main():
    args = sys.argv[1:]
    platform_override = None

    positional = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        elif arg.startswith("--platform="):
            platform_override = arg.split("=", 1)[1]
            i += 1
        elif arg == "--platform" and i + 1 < len(args):
            platform_override = args[i + 1]
            i += 2
        elif arg.startswith("--baseline"):
            i += 2 if arg == "--baseline" else 1
        else:
            positional.append(arg)
            i += 1

    if not positional:
        print(json.dumps({"error": "usage: normalize_metrics.py <input.json> [--platform douyin/kuaishou/xhs]"}, ensure_ascii=False))
        sys.exit(1)

    input_path = positional[0]

    try:
        data = load_input(input_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(2)

    platform = platform_override or data.get("platform", "unknown")
    videos = data.get("videos", [])
    if not videos:
        print(json.dumps({"error": "empty videos list", "platform": platform}, ensure_ascii=False))
        sys.exit(0)

    buckets_data: dict[str, list[dict]] = {}
    for v in videos:
        fc = v.get("follower_count", 0)
        b = bucket_name(fc)
        buckets_data.setdefault(b, []).append(v)

    output_videos = []
    for b, b_videos in buckets_data.items():
        views_list = [vv.get("metrics", {}).get("views", 0) for vv in b_videos if vv.get("metrics", {}).get("views", 0) > 0]
        er_list = [compute_engagement_rate(vv) for vv in b_videos]
        er_list = [e for e in er_list if e is not None]

        medians = {
            "views": compute_median(views_list),
            "engagement_rate": compute_median(er_list),
        }

        for vv in b_videos:
            result = normalize_video(vv, medians)
            result["bucket"] = b
            output_videos.append(result)

    output_videos.sort(key=lambda v: v.get("vs_baseline", {}).get("views_multiple") or 0, reverse=True)

    print(json.dumps({
        "platform": platform,
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "total_videos": len(output_videos),
        "buckets": sorted(set(v["bucket"] for v in output_videos)),
        "videos": output_videos,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
