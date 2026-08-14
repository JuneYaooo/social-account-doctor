"""TikHub REST API client used by the bundled ``tikhub`` CLI.

This module deliberately does not use MCP. Calls go directly to TikHub's
documented REST endpoints under ``/api/v1`` with Bearer authentication.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API_BASE_URL = "https://api.tikhub.io"
HEALTH_PATH = "/api/v1/health/check"
OPENAPI_PATH = "/openapi.json"
ENV_VAR = "TIKHUB_API_KEY"
BASE_URL_ENV_VAR = "TIKHUB_API_BASE_URL"
SKILL_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
LEGACY_ENV_FILE = Path.home() / ".claude" / ".env"
REFERENCES_DIR = Path(__file__).resolve().parents[1] / "references"
CLIENT_NAME = "tikhub-rest-cli"
CLIENT_VERSION = "0.2.0"
USER_AGENT = f"{CLIENT_NAME}/{CLIENT_VERSION} (+https://api.tikhub.io)"
DEFAULT_PLATFORMS = (
    "douyin",
    "xiaohongshu",
    "kuaishou",
    "wechat",
    "bilibili",
    "tiktok",
    "instagram",
    "weibo",
    "youtube",
    "zhihu",
    "linkedin",
    "reddit",
    "twitter",
    "threads",
)
DEBUG = os.environ.get("TIKHUB_DEBUG") == "1"


class TikhubError(Exception):
    """Raised on REST transport, authentication, or upstream errors."""


def _debug(message: str) -> None:
    if DEBUG:
        print(f"[tikhub-rest] {message}", file=sys.stderr)


def _read_env_value(env_file: Path, key: str) -> str | None:
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def load_api_key() -> str:
    """Load the key from process env, explicit file, Skill file, or legacy file."""
    key = os.environ.get(ENV_VAR)
    if key:
        return key.strip()
    configured_file = os.environ.get("TIKHUB_ENV_FILE")
    candidates = [Path(configured_file).expanduser()] if configured_file else []
    candidates.extend((SKILL_ENV_FILE, LEGACY_ENV_FILE))
    for env_file in candidates:
        value = _read_env_value(env_file, ENV_VAR)
        if value:
            return value
    raise TikhubError(f"missing {ENV_VAR}. Set the env var or add it to {SKILL_ENV_FILE}")


def api_base_url() -> str:
    return os.environ.get(BASE_URL_ENV_VAR, DEFAULT_API_BASE_URL).strip().rstrip("/")


def _json_query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _decode_json(body: bytes, label: str) -> Any:
    text = body.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TikhubError(f"{label} returned non-JSON: {text[:500]}") from exc


def _load_catalog(platform: str) -> list[dict]:
    path = REFERENCES_DIR / f"tools-{platform}.json"
    if not path.is_file():
        raise TikhubError(
            f"no REST catalog for {platform!r}; run "
            f"python3 {REFERENCES_DIR.parent}/scripts/refresh_tools.py {platform}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TikhubError(f"invalid REST catalog {path}: {exc}") from exc
    if not isinstance(data, list):
        raise TikhubError(f"invalid REST catalog shape: {path}")
    return data


class TikhubClient:
    def __init__(self, platform: str, api_key: str | None = None, timeout: int = 60):
        self.platform = platform
        self.api_key = api_key or load_api_key()
        self.timeout = max(10, min(int(timeout), 60))
        self.base_url = api_base_url()

    def list_tools(self) -> list[dict]:
        """Return the cached REST endpoint catalog for this platform."""
        return _load_catalog(self.platform)

    def _tool(self, tool_name: str) -> dict:
        for tool in self.list_tools():
            if tool.get("name") == tool_name:
                return tool
        raise TikhubError(
            f"REST endpoint {tool_name!r} not found in {self.platform} catalog; "
            f"use `tikhub list {self.platform}` and update the command"
        )

    def _request(
        self,
        method: str,
        path: str,
        arguments: dict,
        query_names: set[str],
        path_names: set[str],
    ) -> Any:
        method = method.upper()
        query = {}
        body_args = {}
        for key, value in arguments.items():
            if key in path_names:
                path = path.replace(f"{{{key}}}", urllib.parse.quote(str(value), safe=""))
            elif method == "GET" or key in query_names:
                query[key] = _json_query_value(value)
            else:
                body_args[key] = value
        unresolved = re.findall(r"{([^}]+)}", path)
        if unresolved:
            raise TikhubError(f"missing REST path parameter(s): {', '.join(unresolved)}")

        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        data = None
        if method != "GET":
            headers["Content-Type"] = "application/json"
            data = json.dumps(body_args, ensure_ascii=False).encode("utf-8")

        for attempt in range(1, 4):
            _debug(f"{method} {path} attempt={attempt}")
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return _decode_json(response.read(), f"{method} {path}")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                if attempt < 3 and (exc.code == 429 or exc.code >= 500):
                    time.sleep(0.5 * attempt)
                    continue
                raise TikhubError(f"HTTP {exc.code} from {path}: {body[:500]}") from exc
            except urllib.error.URLError as exc:
                if attempt < 3:
                    time.sleep(0.5 * attempt)
                    continue
                raise TikhubError(f"network error calling {path}: {exc.reason}") from exc
        raise TikhubError(f"REST call failed after retries: {path}")

    def call(self, tool_name: str, arguments: dict | None = None) -> Any:
        """Call one cached REST endpoint using query/body metadata from OpenAPI."""
        tool = self._tool(tool_name)
        path = str(tool.get("path") or "")
        method = str(tool.get("method") or "GET")
        if not path.startswith("/api/v1/"):
            raise TikhubError(f"refusing non-REST endpoint path: {path!r}")
        query_names = {str(name) for name in tool.get("queryParameters", [])}
        path_names = {str(name) for name in tool.get("pathParameters", [])}
        return self._request(method, path, arguments or {}, query_names, path_names)


def _get_public_json(path: str, label: str) -> Any:
    url = f"{api_base_url()}{path}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return _decode_json(response.read(), label)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise TikhubError(f"{label} failed: {exc}") from exc


def health() -> dict:
    """Call TikHub's documented REST health endpoint."""
    result = _get_public_json(HEALTH_PATH, "REST health check")
    if not isinstance(result, dict):
        raise TikhubError(f"REST health check returned unexpected data: {result!r}")
    return result


def openapi() -> dict:
    result = _get_public_json(OPENAPI_PATH, "REST OpenAPI discovery")
    if not isinstance(result, dict) or "paths" not in result:
        raise TikhubError("REST OpenAPI discovery returned invalid schema")
    return result


def platforms() -> list[str]:
    """Return CLI-supported REST catalog groups without a network request."""
    return list(DEFAULT_PLATFORMS)
