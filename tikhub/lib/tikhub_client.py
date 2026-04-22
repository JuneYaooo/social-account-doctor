"""tikhub_client — minimal stdlib JSON-RPC client for https://mcp.tikhub.io.

Speaks MCP-over-HTTP: initialize → cache session id → tools/list / tools/call.
Response transport is SSE (text/event-stream); we parse `data: {...}` lines.

Public API:
    client = TikhubClient(platform="douyin")
    client.call(tool_name, arguments_dict) -> parsed result (dict/list/str)
    client.list_tools() -> [{"name", "description", "inputSchema", ...}, ...]
    client.health() -> dict
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENDPOINT = "https://mcp.tikhub.io/{platform}/mcp"
HEALTH_URL = "https://mcp.tikhub.io/health"
PLATFORMS_URL = "https://mcp.tikhub.io/platforms"

SESSION_DIR = Path("/tmp")
SESSION_TTL_SECONDS = 300  # 5 min — server-side TTL is unknown; refresh proactively

ENV_FILE = Path.home() / ".claude" / ".env"
ENV_VAR = "TIKHUB_API_KEY"

PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "tikhub-cli"
CLIENT_VERSION = "0.1.0"
USER_AGENT = f"{CLIENT_NAME}/{CLIENT_VERSION} (+https://mcp.tikhub.io)"

DEBUG = os.environ.get("TIKHUB_DEBUG") == "1"


class TikhubError(Exception):
    """Raised on transport / protocol / upstream errors."""


def _debug(msg: str) -> None:
    if DEBUG:
        print(f"[tikhub] {msg}", file=sys.stderr)


def load_api_key() -> str:
    """Env var TIKHUB_API_KEY wins; fall back to ~/.claude/.env."""
    key = os.environ.get(ENV_VAR)
    if key:
        return key.strip()
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == ENV_VAR:
                return v.strip().strip('"').strip("'")
    raise TikhubError(
        f"missing {ENV_VAR}. Set env var or add `{ENV_VAR}=...` to {ENV_FILE}"
    )


def _parse_sse(body: bytes) -> dict:
    """Pull the first `data: {...}` JSON object out of an SSE stream.

    tikhub returns one event per response, so first match is the answer.
    """
    text = body.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if not payload:
                continue
            try:
                return json.loads(payload)
            except json.JSONDecodeError as e:
                raise TikhubError(f"bad SSE JSON: {e}\nraw: {payload[:500]}")
    # Maybe upstream returned plain JSON despite Accept header
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise TikhubError(f"no SSE data in response. raw: {text[:500]}")


def _maybe_unwrap_text(value: Any) -> Any:
    """If value is a JSON-stringified scalar/object, parse it once."""
    if isinstance(value, str):
        s = value.strip()
        if s and s[0] in "{[":
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return value
    return value


class TikhubClient:
    def __init__(self, platform: str, api_key: str | None = None, timeout: int = 60):
        self.platform = platform
        self.endpoint = ENDPOINT.format(platform=platform)
        self.api_key = api_key or load_api_key()
        self.timeout = timeout
        self._req_id = 0

    # ---------- session ----------

    @property
    def _session_file(self) -> Path:
        return SESSION_DIR / f".tikhub-session-{self.platform}.json"

    def _load_session(self) -> str | None:
        f = self._session_file
        if not f.is_file():
            return None
        try:
            data = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - data.get("created_at", 0) > SESSION_TTL_SECONDS:
            _debug(f"session for {self.platform} expired (age > {SESSION_TTL_SECONDS}s)")
            return None
        return data.get("session_id")

    def _save_session(self, session_id: str) -> None:
        try:
            self._session_file.write_text(
                json.dumps({"session_id": session_id, "created_at": time.time()})
            )
        except OSError as e:
            _debug(f"could not cache session: {e}")

    def _drop_session(self) -> None:
        try:
            self._session_file.unlink(missing_ok=True)
        except OSError:
            pass

    # ---------- HTTP ----------

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _post(self, payload: dict, session_id: str | None) -> tuple[dict, dict]:
        """POST and return (parsed_body, response_headers_lowercased)."""
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        _debug(f"POST {self.endpoint} method={payload.get('method')} session={session_id}")
        req = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_body = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise TikhubError(f"HTTP {e.code}: {err_body[:500]}")
        except urllib.error.URLError as e:
            raise TikhubError(f"network error: {e.reason}")
        parsed = _parse_sse(resp_body)
        return parsed, resp_headers

    # ---------- protocol ----------

    def initialize(self) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        }
        data, headers = self._post(payload, session_id=None)
        if "error" in data:
            raise TikhubError(f"initialize failed: {data['error']}")
        session_id = headers.get("mcp-session-id")
        if not session_id:
            raise TikhubError("initialize: server did not return mcp-session-id header")
        self._save_session(session_id)
        _debug(f"initialized {self.platform} session={session_id}")
        return session_id

    def _ensure_session(self) -> str:
        return self._load_session() or self.initialize()

    def _call_jsonrpc(self, method: str, params: dict) -> Any:
        """One retry on session-related failure: drop cache, re-init, retry."""
        for attempt in (1, 2):
            session_id = self._ensure_session()
            payload = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": params,
            }
            try:
                data, _headers = self._post(payload, session_id=session_id)
            except TikhubError as e:
                msg = str(e).lower()
                if attempt == 1 and ("session" in msg or "401" in msg or "440" in msg):
                    _debug("session looks invalid; refreshing and retrying")
                    self._drop_session()
                    continue
                raise
            if "error" in data:
                err = data["error"]
                # JSON-RPC -32001/-32600 etc. could indicate bad session — retry once
                if attempt == 1 and isinstance(err, dict):
                    msg = (err.get("message") or "").lower()
                    if "session" in msg:
                        self._drop_session()
                        continue
                raise TikhubError(f"{method} failed: {err}")
            return data.get("result")

    # ---------- public ----------

    def list_tools(self) -> list[dict]:
        """Return the full tools catalog (handles cursor pagination if present)."""
        all_tools: list[dict] = []
        cursor = None
        while True:
            params: dict = {}
            if cursor:
                params["cursor"] = cursor
            result = self._call_jsonrpc("tools/list", params)
            if not isinstance(result, dict):
                raise TikhubError(f"tools/list bad shape: {result!r}")
            all_tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return all_tools

    def call(self, tool_name: str, arguments: dict | None = None) -> Any:
        """Call a tool. Returns the parsed result payload (auto-unwrapped)."""
        result = self._call_jsonrpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )
        if not isinstance(result, dict):
            return result
        # Prefer structuredContent (already-typed); fall back to content[0].text
        if "structuredContent" in result and result["structuredContent"] is not None:
            sc = result["structuredContent"]
            if isinstance(sc, dict) and "result" in sc and len(sc) == 1:
                return _maybe_unwrap_text(sc["result"])
            return sc
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                return _maybe_unwrap_text(first.get("text", ""))
        return result


def _get_json(url: str, label: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        raise TikhubError(f"{label} failed: {e}")


def health() -> dict:
    """Hit /health (no auth required)."""
    return _get_json(HEALTH_URL, "health check")


def platforms() -> Any:
    """Hit /platforms (no auth required)."""
    return _get_json(PLATFORMS_URL, "platforms check")
