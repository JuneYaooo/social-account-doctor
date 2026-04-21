#!/usr/bin/env python3
"""
account-diagnostic: dispatch_account.py
账号 URL → 平台识别 → 提示该调哪个 tikhub MCP 工具拿账号信息 + 笔记列表。

不直接调 MCP（MCP 调用要走 Claude）。本脚本只做：
1. 解析 URL，识别平台（仅支持小红书 / 抖音 / 快手）
2. 提取 user_id / sec_user_id / username（平台不同字段不同）
3. 输出 JSON：告诉 caller platform / user_id / 要调哪个 tikhub MCP 工具

caller 拿到 JSON 后，自己去调对应 tikhub MCP，再把账号信息 + 笔记列表回填给诊断流程。

用法:
    dispatch_account.py <账号URL>

示例 URL:
    小红书 web:    https://www.xiaohongshu.com/user/profile/5e7f...abc
    小红书短链:    https://xhslink.com/A/xxxxx
    抖音 web:      https://www.douyin.com/user/MS4wLjABAAAA...
    抖音短链:      https://v.douyin.com/xxxxx
    快手 web:      https://www.kuaishou.com/profile/3xabcdef...
"""

import json
import re
import sys
from urllib.parse import urlparse


PLATFORM_RULES = [
    {
        "platform": "xiaohongshu",
        "host_patterns": [r"xhslink\.com", r"xiaohongshu\.com"],
        "id_extractors": [
            (r"/user/profile/([a-z0-9]+)", "user_id"),
            (r"/profile/([a-z0-9]+)", "user_id"),
        ],
        "tools": {
            "extract_share": "mcp__tikhub-xiaohongshu__xiaohongshu_app_get_user_id_and_xsec_token",
            "user_info": "mcp__tikhub-xiaohongshu__xiaohongshu_app_v2_get_user_info",
            "user_notes": "mcp__tikhub-xiaohongshu__xiaohongshu_app_v2_get_user_posted_notes",
            "user_faved": "mcp__tikhub-xiaohongshu__xiaohongshu_app_v2_get_user_faved_notes",
            "note_detail": "mcp__tikhub-xiaohongshu__xiaohongshu_web_v2_fetch_feed_notes_v2",
            "note_comments": "mcp__tikhub-xiaohongshu__xiaohongshu_web_v2_fetch_note_comments",
            "search_notes": "mcp__tikhub-xiaohongshu__xiaohongshu_app_v2_search_notes",
            "search_users": "mcp__tikhub-xiaohongshu__xiaohongshu_app_v2_search_users",
            "hot_list": "mcp__tikhub-xiaohongshu__xiaohongshu_web_v2_fetch_hot_list",
        },
        "needs_share_resolve": True,
        "id_field": "user_id",
        "extra_param_note": "小红书 V2 接口可能需要 xsec_token，先调 extract_share 拿全套字段",
    },
    {
        "platform": "douyin",
        "host_patterns": [r"douyin\.com", r"iesdouyin\.com", r"v\.douyin\.com"],
        "id_extractors": [
            (r"/user/(MS4wLjABAAAA[\w-]+)", "sec_user_id"),
            (r"/share/user/(MS4wLjABAAAA[\w-]+)", "sec_user_id"),
        ],
        "tools": {
            "share_resolve": "mcp__tikhub-douyin__douyin_app_v3_fetch_one_video_by_share_url",
            "user_info_by_sec": "mcp__tikhub-douyin__douyin_web_handler_user_profile",
            "user_info_by_uid": "mcp__tikhub-douyin__douyin_web_handler_user_profile_v3",
            "user_info_by_unique": "mcp__tikhub-douyin__douyin_web_handler_user_profile_v2",
            "user_post_videos": "mcp__tikhub-douyin__douyin_web_fetch_user_post_videos",
            "user_like_videos": "mcp__tikhub-douyin__douyin_web_fetch_user_like_videos",
            "video_detail": "mcp__tikhub-douyin__douyin_app_v3_fetch_one_video",
            "video_statistics": "mcp__tikhub-douyin__douyin_app_v3_fetch_video_statistics",
            "video_play_url": "mcp__tikhub-douyin__douyin_app_v3_fetch_video_high_quality_play_url",
            "video_comments": "mcp__tikhub-douyin__douyin_app_v3_fetch_video_comments",
            "search_users": "mcp__tikhub-douyin__douyin_app_v3_fetch_user_search_result",
            "search_videos": "mcp__tikhub-douyin__douyin_app_v3_fetch_video_search_result_v2",
            "hot_list": "mcp__tikhub-douyin__douyin_app_v3_fetch_hot_search_list",
            "fans_portrait": "mcp__tikhub-douyin__douyin_billboard_fetch_hot_account_fans_portrait_list",
        },
        "needs_share_resolve": True,
        "id_field": "sec_user_id",
        "extra_param_note": "抖音必须用 sec_user_id (MS4wLjABAAAA开头)，不是 uid。短链需先调 share_resolve",
    },
    {
        "platform": "kuaishou",
        "host_patterns": [r"kuaishou\.com", r"v\.kuaishou\.com", r"chenzhongtech\.com"],
        "id_extractors": [
            (r"/profile/([a-zA-Z0-9_-]+)", "user_id"),
            (r"/userProfile/([a-zA-Z0-9_-]+)", "user_id"),
        ],
        "tools": {
            "extract_share": "mcp__tikhub-kuaishou__kuaishou_web_fetch_get_user_id",
            "user_info_app": "mcp__tikhub-kuaishou__kuaishou_app_fetch_one_user_v2",
            "user_info_web": "mcp__tikhub-kuaishou__kuaishou_web_fetch_user_info",
            "user_post": "mcp__tikhub-kuaishou__kuaishou_app_fetch_user_post_v2",
            "user_hot_post": "mcp__tikhub-kuaishou__kuaishou_app_fetch_user_hot_post",
            "user_live_info": "mcp__tikhub-kuaishou__kuaishou_app_fetch_user_live_info",
            "video_detail": "mcp__tikhub-kuaishou__kuaishou_app_fetch_one_video",
            "video_comments": "mcp__tikhub-kuaishou__kuaishou_app_fetch_one_video_comment",
            "search_users": "mcp__tikhub-kuaishou__kuaishou_app_search_user_v2",
            "search_videos": "mcp__tikhub-kuaishou__kuaishou_app_search_video_v2",
            "hot_list": "mcp__tikhub-kuaishou__kuaishou_web_fetch_kuaishou_hot_list_v2",
        },
        "needs_share_resolve": True,
        "id_field": "user_id",
        "extra_param_note": "快手 user_id 是字符串，翻页用 pcursor。app/web 接口可互相验证",
    },
]


def detect_platform(url: str) -> dict:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    full = url.lower()

    for rule in PLATFORM_RULES:
        for pat in rule["host_patterns"]:
            if re.search(pat, host) or re.search(pat, full):
                return rule
    return None


def extract_id(url: str, rule: dict) -> dict:
    found = {}
    for pat, name in rule["id_extractors"]:
        m = re.search(pat, url)
        if m:
            found[name] = m.group(1)
    return found


def main():
    if len(sys.argv) != 2:
        print(json.dumps({
            "error": "usage: dispatch_account.py <账号URL>",
            "supported": [r["platform"] for r in PLATFORM_RULES],
        }, ensure_ascii=False))
        sys.exit(1)

    url = sys.argv[1].strip()
    rule = detect_platform(url)

    if not rule:
        print(json.dumps({
            "error": "unsupported platform (only 小红书 / 抖音 / 快手 are supported)",
            "url": url,
            "supported": [r["platform"] for r in PLATFORM_RULES],
            "hint": "如果是短链/微信分享文本，可能需要用户先粘贴完整 URL，或直接告诉你 user_id",
        }, ensure_ascii=False))
        sys.exit(2)

    ids = extract_id(url, rule)
    primary_id = ids.get(rule["id_field"])
    needs_resolve = rule["needs_share_resolve"] and not primary_id

    if needs_resolve and "extract_share" in rule["tools"]:
        next_step = (
            f"短链/无 ID — 先调 MCP 工具 `{rule['tools']['extract_share']}` "
            f"(传 share_link={url}) 解析出 {rule['id_field']}"
        )
    elif primary_id:
        primary_tool = None
        for k in ("user_info_app", "user_info", "user_info_by_sec", "user_info_web"):
            if k in rule["tools"]:
                primary_tool = rule["tools"][k]
                break
        next_step = (
            f"已识别 {rule['id_field']}={primary_id} — "
            f"直接调 MCP 工具 `{primary_tool}` 拿账号信息"
        )
    else:
        next_step = (
            f"URL 解析不出 {rule['id_field']}，建议让用户提供:"
            f"(1) 完整账号主页 URL，或 (2) 直接给 {rule['id_field']}"
        )

    output = {
        "platform": rule["platform"],
        "url": url,
        "ids": ids,
        "primary_id_field": rule["id_field"],
        "primary_id": primary_id,
        "tools": rule["tools"],
        "needs_share_resolve": needs_resolve,
        "extra_param_note": rule["extra_param_note"],
        "next_step": next_step,
        "playbook": (
            "1. caller 按 next_step 调 tikhub MCP 拿账号基本信息（粉丝数 / 简介 / 认证）\n"
            "2. caller 调 user_post / user_notes 拿最近 30 条作品\n"
            "3. caller 算爆款率 / 扑街率 / 互动均值（SKILL.md §1 Layer 2）\n"
            "4. caller 抽 top 3 + bottom 3，对每条调 video_detail / note_detail 拿封面 + 媒体 URL\n"
            "5. caller 下载封面 / 视频前 10s，调 scripts/analyze_image.py 或 scripts/analyze_video.py\n"
            "6. caller 套 platforms/{平台}.md 6 维评分 + 行动清单\n"
            "7. caller 按 SKILL.md §6 模板输出报告"
        ),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
