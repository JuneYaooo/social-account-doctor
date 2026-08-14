#!/usr/bin/env python3
"""Refresh REST endpoint catalogs from TikHub's public OpenAPI schema.

Generated catalogs map stable CLI endpoint names to methods and ``/api/v1`` paths.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from tikhub_client import TikhubError, openapi  # noqa: E402


REFERENCES_DIR = HERE.parent / "references"
DEFAULT_PLATFORMS = ("douyin", "xiaohongshu", "kuaishou", "wechat", "bilibili")
GROUP_PREFIXES = {
    "douyin": ("douyin/",),
    "xiaohongshu": ("xiaohongshu/",),
    "kuaishou": ("kuaishou/",),
    "wechat": ("wechat/", "wechat_channels/", "wechat_mp/", "wechat_search/"),
    "bilibili": ("bilibili/",),
    "tiktok": ("tiktok/",),
    "instagram": ("instagram/",),
    "weibo": ("weibo/",),
    "youtube": ("youtube/",),
    "zhihu": ("zhihu/",),
    "linkedin": ("linkedin/",),
    "reddit": ("reddit/",),
    "twitter": ("twitter/",),
    "threads": ("threads/",),
}


def _resolve_ref(schema: dict, document: dict) -> dict:
    ref = schema.get("$ref") if isinstance(schema, dict) else None
    if not isinstance(ref, str) or not ref.startswith("#/components/schemas/"):
        return schema if isinstance(schema, dict) else {}
    name = ref.rsplit("/", 1)[-1]
    resolved = document.get("components", {}).get("schemas", {}).get(name, {})
    return resolved if isinstance(resolved, dict) else {}


def _schema_for_operation(operation: dict, document: dict) -> tuple[dict, list[str], list[str]]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    query_parameters: list[str] = []
    path_parameters: list[str] = []
    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict) or not parameter.get("name"):
            continue
        name = str(parameter["name"])
        schema = _resolve_ref(parameter.get("schema", {}), document)
        properties[name] = schema
        if parameter.get("required"):
            required.append(name)
        location = parameter.get("in")
        if location == "query":
            query_parameters.append(name)
        elif location == "path":
            path_parameters.append(name)

    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {}) if isinstance(request_body, dict) else {}
    body_schema = content.get("application/json", {}).get("schema", {}) if isinstance(content, dict) else {}
    body_schema = _resolve_ref(body_schema, document)
    for name, schema in body_schema.get("properties", {}).items():
        properties.setdefault(str(name), _resolve_ref(schema, document))
    for name in body_schema.get("required", []):
        if name not in required:
            required.append(name)

    input_schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        input_schema["required"] = required
    return input_schema, query_parameters, path_parameters


def _canonical_name(path: str) -> str:
    relative = path.removeprefix("/api/v1/").strip("/")
    relative = re.sub(r"[{}]", "", relative)
    return re.sub(r"[^A-Za-z0-9_]+", "_", relative.replace("/", "_")).strip("_")


def _belongs_to(platform: str, path: str) -> bool:
    relative = path.removeprefix("/api/v1/")
    return any(relative.startswith(prefix) for prefix in GROUP_PREFIXES.get(platform, (f"{platform}/",)))


def build_catalog(document: dict, platform: str) -> list[dict]:
    tools = []
    for path, path_item in document.get("paths", {}).items():
        if not path.startswith("/api/v1/") or not _belongs_to(platform, path):
            continue
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            input_schema, query_parameters, path_parameters = _schema_for_operation(operation, document)
            tools.append(
                {
                    "name": _canonical_name(path),
                    "description": operation.get("summary") or operation.get("description") or "",
                    "method": method.upper(),
                    "path": path,
                    "inputSchema": input_schema,
                    "queryParameters": query_parameters,
                    "pathParameters": path_parameters,
                }
            )
    return sorted(tools, key=lambda item: item["name"])


def refresh(document: dict, platform: str) -> int:
    tools = build_catalog(document, platform)
    REFERENCES_DIR.mkdir(parents=True, exist_ok=True)
    output = REFERENCES_DIR / f"tools-{platform}.json"
    output.write_text(json.dumps(tools, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{platform}] wrote {len(tools)} REST endpoint(s) -> {output}", file=sys.stderr)
    return len(tools)


def main() -> None:
    args = sys.argv[1:]
    targets = list(GROUP_PREFIXES) if args == ["--all"] else (args or list(DEFAULT_PLATFORMS))
    unknown = [platform for platform in targets if platform not in GROUP_PREFIXES]
    if unknown:
        print(f"unknown platform group(s): {', '.join(unknown)}", file=sys.stderr)
        sys.exit(2)
    try:
        document = openapi()
    except TikhubError as exc:
        print(f"OpenAPI refresh failed: {exc}", file=sys.stderr)
        sys.exit(2)
    total = sum(refresh(document, platform) for platform in targets)
    print(f"Total: {total} REST endpoint(s) across {len(targets)} platform(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
