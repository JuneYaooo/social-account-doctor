# TikHub direct REST CLI

This directory bundles the TikHub REST CLI used by `social-account-doctor`. It
calls TikHub's documented `/api/v1/...` endpoints directly and uses the public
OpenAPI document to maintain local endpoint catalogs.

```text
tikhub/
├── bin/tikhub                       # CLI entry point
├── lib/tikhub_client.py             # REST client (Python standard library)
├── references/tools-{platform}.json # cached OpenAPI endpoint catalogs
└── scripts/refresh_tools.py         # refresh catalogs from /openapi.json
```

## Configuration

Create the repository or installed Skill `.env` from `.env.example` and set:

```text
TIKHUB_API_KEY=your_api_key
```

The client sends `Authorization: Bearer <key>`. The default API base URL is
`https://api.tikhub.io`; use `TIKHUB_API_BASE_URL=https://api.tikhub.dev` when
the mainland endpoint is preferable. `TIKHUB_ENV_FILE` can point to an explicit
environment file.

## Usage

```bash
tikhub --health
tikhub --platforms
tikhub list xiaohongshu search
tikhub describe douyin douyin_web_fetch_one_video
tikhub douyin douyin_web_fetch_one_video --aweme_id 1234567890
tikhub xiaohongshu xiaohongshu_app_v2_search_notes \
  --json '{"keyword":"早餐","page":"1"}'
```

Numeric-looking IDs remain strings unless an explicit CLI type tag is used.
Use `--page:int=1` only when the endpoint schema actually requires an integer.

## Endpoint catalogs

Catalogs are generated from `https://api.tikhub.io/openapi.json`:

```bash
python3 tikhub/scripts/refresh_tools.py
python3 tikhub/scripts/refresh_tools.py douyin xiaohongshu
python3 tikhub/scripts/refresh_tools.py --all
```

Each catalog entry records the HTTP method, REST path, query/path parameter
locations, and request schema. Calls whose catalog path is outside `/api/v1/`
are rejected by the client.

## Errors

| Symptom | Resolution |
|---|---|
| `missing TIKHUB_API_KEY` | Set the variable or configure the Skill `.env` |
| `HTTP 401` | Replace an invalid or expired API key |
| `HTTP 429` | Reduce concurrency; the client retries transient limits |
| endpoint not found | Run `tikhub list`, then refresh the OpenAPI catalog if needed |

Use `TIKHUB_DEBUG=1` to print request method/path and retry attempts to stderr.
