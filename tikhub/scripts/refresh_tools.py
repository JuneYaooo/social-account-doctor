#!/usr/bin/env python3
"""refresh_tools — pull /tools/list per platform and cache as references/tools-{platform}.json.

Usage:
    refresh_tools.py                # all default platforms
    refresh_tools.py douyin xhs     # specific platforms
    refresh_tools.py --all          # try every platform tikhub /platforms returns
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from tikhub_client import TikhubClient, TikhubError, platforms as fetch_platforms  # noqa: E402

REFERENCES_DIR = HERE.parent / "references"

DEFAULT_PLATFORMS = ("douyin", "xiaohongshu", "kuaishou", "wechat", "bilibili")


def refresh(platform: str) -> int:
    print(f"[{platform}] fetching tools/list ...", file=sys.stderr)
    try:
        client = TikhubClient(platform=platform)
        tools = client.list_tools()
    except TikhubError as e:
        print(f"[{platform}] FAILED: {e}", file=sys.stderr)
        return 0
    REFERENCES_DIR.mkdir(parents=True, exist_ok=True)
    out = REFERENCES_DIR / f"tools-{platform}.json"
    out.write_text(json.dumps(tools, ensure_ascii=False, indent=2))
    print(f"[{platform}] wrote {len(tools)} tool(s) → {out}", file=sys.stderr)
    return len(tools)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        targets = list(DEFAULT_PLATFORMS)
    elif args == ["--all"]:
        try:
            data = fetch_platforms()
        except TikhubError as e:
            print(f"could not list platforms: {e}", file=sys.stderr)
            sys.exit(2)
        # /platforms returns a list of dicts; key may be 'name' or 'id' — try both
        targets = []
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    name = entry.get("name") or entry.get("id") or entry.get("platform")
                    if name:
                        targets.append(str(name).lower())
                elif isinstance(entry, str):
                    targets.append(entry.lower())
        elif isinstance(data, dict):
            targets = [str(k).lower() for k in data.keys()]
        if not targets:
            print(f"unexpected /platforms shape: {data!r}", file=sys.stderr)
            sys.exit(2)
    else:
        targets = args

    total = 0
    for p in targets:
        total += refresh(p)
    print(f"\nTotal: {total} tool(s) cached across {len(targets)} platform(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
