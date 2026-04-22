# tikhub/ — bundled HTTP CLI

This directory bundles the **tikhub HTTP CLI wrapper** so `social-account-doctor` is
fully self-contained — no external skill dependency.

```
tikhub/
├── bin/tikhub                       # CLI entry point (chmod +x)
├── lib/tikhub_client.py             # HTTP JSON-RPC + SSE + session cache (pure stdlib)
├── references/tools-{platform}.json # cached /tools/list catalogs (5 platforms, ~330KB)
└── scripts/refresh_tools.py         # rebuild references/ from live tikhub
```

## Why bundled?

Earlier the wrapper lived in a separate `tikhub-api` skill at `~/.claude/skills/tikhub-api/`.
That skill is **not published** on github. To make `social-account-doctor` standalone for
distribution, the wrapper is copied here.

## Quick install (after `git clone social-account-doctor`)

```bash
# 1. API key in ~/.claude/.env (chmod 600)
mkdir -p ~/.claude
cat >> ~/.claude/.env <<'EOF'
TIKHUB_API_KEY=YOUR_KEY_FROM_https://tikhub.io
EOF
chmod 600 ~/.claude/.env

# 2. Symlink to PATH
ln -sf "$(pwd)/tikhub/bin/tikhub" ~/.local/bin/tikhub

# 3. Verify
tikhub --health
tikhub list xiaohongshu search
```

## Usage

```bash
tikhub <platform> <tool_name> --key1 value1 --key2 value2
tikhub <platform> <tool_name> --json '{"k":"v"}'

tikhub list <platform> [substring]      # browse cached tool catalog
tikhub describe <platform> <tool_name>  # full input schema
tikhub --health                         # connectivity check
tikhub --platforms                      # list available tikhub platforms
```

Supported platforms (cached): `xiaohongshu` / `douyin` / `kuaishou` / `wechat` / `bilibili`.
Add others (`tiktok`, `instagram`, `weibo`, `youtube`, `zhihu`, etc.) with:

```bash
python3 tikhub/scripts/refresh_tools.py tiktok
```

## Protocol notes

- HTTP endpoint: `https://mcp.tikhub.io/{platform}/mcp`
- MCP `2024-11-05` over HTTP: `initialize` returns `Mcp-Session-Id` header → `tools/list` / `tools/call`
- Response is **SSE** (`text/event-stream`); wrapper parses `data: {...}` lines
- Session cached at `/tmp/.tikhub-session-{platform}.json` (5 min TTL); invalid → re-init + retry once
- Must send `User-Agent` header (Cloudflare blocks default `Python-urllib/3.x`)

## Errors

| Symptom | Fix |
|---|---|
| `missing TIKHUB_API_KEY` | Check `~/.claude/.env`; `chmod 600 ~/.claude/.env` |
| `HTTP 401` | Bad/expired key → regenerate at https://user.tikhub.io |
| `HTTP 429` | Rate limit (10 RPS); cap concurrency ≤ 3 |
| `RetryError[<HTTPStatusError>]` | Upstream tikhub flakiness; rotate to fallback tool (see search skill docs) |
| `tool 'X' not found in catalog` | Cache stale → `python3 tikhub/scripts/refresh_tools.py <platform>` |

## Debugging

```bash
TIKHUB_DEBUG=1 tikhub <platform> <tool> ...   # log requests to stderr
```

## License + provenance

Vendored from `tikhub-api` skill, MIT. Original: see https://github.com/JuneYaooo/social-account-doctor.
