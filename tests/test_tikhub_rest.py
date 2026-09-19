import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_client():
    path = REPO_ROOT / "tikhub" / "lib" / "tikhub_client.py"
    spec = importlib.util.spec_from_file_location("tikhub_client_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # 默认缓存落在 cwd 的 ./output/cache/tikhub —— 测试模块一律指到临时目录并
    # 关闭，防止假响应写进真实缓存、污染下一次运行（缓存相关用例会显式打开）
    module._CACHE_DIR = Path(tempfile.mkdtemp(prefix="sad-tikhub-cache-")) / "cache"
    module._cache_enabled = False
    return module


def load_refresh(client_module):
    path = REPO_ROOT / "tikhub" / "scripts" / "refresh_tools.py"
    previous = sys.modules.get("tikhub_client")
    sys.modules["tikhub_client"] = client_module
    try:
        spec = importlib.util.spec_from_file_location("refresh_tools_under_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("tikhub_client", None)
        else:
            sys.modules["tikhub_client"] = previous


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_get_endpoint_uses_query_and_bearer_auth(monkeypatch):
    module = load_client()
    catalog = [{
        "name": "douyin_web_fetch_one_video",
        "method": "GET",
        "path": "/api/v1/douyin/web/fetch_one_video",
        "queryParameters": ["aweme_id", "with_detail"],
        "pathParameters": [],
    }]
    captured = {}
    monkeypatch.setattr(module, "_load_catalog", lambda platform: catalog)

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"code": 200, "data": {"ok": True}})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    result = module.TikhubClient("douyin", api_key="secret").call(
        "douyin_web_fetch_one_video",
        {"aweme_id": "123", "with_detail": True},
    )

    assert result["code"] == 200
    assert captured["request"].method == "GET"
    assert "aweme_id=123" in captured["request"].full_url
    assert "with_detail=true" in captured["request"].full_url
    assert captured["request"].get_header("Authorization") == "Bearer secret"
    assert captured["request"].data is None


def test_post_endpoint_splits_query_and_json_body(monkeypatch):
    module = load_client()
    catalog = [{
        "name": "example_post",
        "method": "POST",
        "path": "/api/v1/douyin/example/{item_id}",
        "queryParameters": ["cursor"],
        "pathParameters": ["item_id"],
    }]
    captured = {}
    monkeypatch.setattr(module, "_load_catalog", lambda platform: catalog)

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse({"code": 200})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    module.TikhubClient("douyin", api_key="secret").call(
        "example_post",
        {"item_id": "a/b", "cursor": "2", "keyword": "蛋糕"},
    )

    request = captured["request"]
    assert request.method == "POST"
    assert "/a%2Fb?cursor=2" in request.full_url
    assert json.loads(request.data) == {"keyword": "蛋糕"}


def test_client_rejects_paths_outside_documented_rest_api(monkeypatch):
    module = load_client()
    monkeypatch.setattr(module, "_load_catalog", lambda platform: [{
        "name": "unsafe",
        "method": "POST",
        "path": "/other/protocol",
        "queryParameters": [],
        "pathParameters": [],
    }])

    with pytest.raises(module.TikhubError, match="refusing non-REST endpoint"):
        module.TikhubClient("douyin", api_key="secret").call("unsafe")


def test_openapi_catalog_preserves_method_and_parameter_locations():
    client = load_client()
    refresh = load_refresh(client)
    document = {
        "paths": {
            "/api/v1/douyin/web/fetch_item/{item_id}": {
                "post": {
                    "summary": "Fetch item",
                    "parameters": [
                        {"name": "item_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "cursor", "in": "query", "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"keyword": {"type": "string"}},
                                    "required": ["keyword"],
                                }
                            }
                        }
                    },
                }
            },
            "/internal/not-supported": {"get": {"summary": "Ignore"}},
        }
    }

    catalog = refresh.build_catalog(document, "douyin")

    assert len(catalog) == 1
    endpoint = catalog[0]
    assert endpoint["name"] == "douyin_web_fetch_item_item_id"
    assert endpoint["method"] == "POST"
    assert endpoint["path"] == "/api/v1/douyin/web/fetch_item/{item_id}"
    assert endpoint["queryParameters"] == ["cursor"]
    assert endpoint["pathParameters"] == ["item_id"]
    assert endpoint["inputSchema"]["required"] == ["item_id", "keyword"]


def test_health_uses_documented_rest_path(monkeypatch):
    module = load_client()
    captured = {}

    def fake_get(path, label):
        captured["path"] = path
        return {"status": "ok"}

    monkeypatch.setattr(module, "_get_public_json", fake_get)
    assert module.health() == {"status": "ok"}
    assert captured["path"] == "/api/v1/health/check"


def test_dispatch_account_only_recommends_cataloged_endpoints():
    dispatch_path = REPO_ROOT / "scripts" / "dispatch_account.py"
    spec = importlib.util.spec_from_file_location("dispatch_account_under_test", dispatch_path)
    dispatch = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(dispatch)

    for rule in dispatch.PLATFORM_RULES:
        catalog_path = REPO_ROOT / "tikhub" / "references" / f"tools-{rule['platform']}.json"
        names = {item["name"] for item in json.loads(catalog_path.read_text())}
        for command in rule["tools"].values():
            endpoint = command.split()[2]
            assert endpoint in names, f"{rule['platform']}: {endpoint} is not in the REST catalog"


def test_client_contains_no_legacy_transport_endpoint():
    source = (REPO_ROOT / "tikhub" / "lib" / "tikhub_client.py").read_text().lower()
    assert "mcp.tikhub.io" not in source
    assert "jsonrpc" not in source
    assert "mcp-session-id" not in source


# ---------------------------------------------------------------------------
# 24h response cache (./output/cache/tikhub/) — same link shouldn't be paid twice
# ---------------------------------------------------------------------------

def _client_with_fake_request(client_module, tmp_path, responses=None):
    """Build a TikhubClient whose catalog + _request are faked; cache dir -> tmp."""
    client_module._CACHE_DIR = tmp_path / "cache"
    client_module._cache_enabled = True
    calls = {"count": 0}

    def fake_request(self, method, path, arguments, query_names, path_names):
        calls["count"] += 1
        return {"data": responses[0] if responses else f"resp-{calls['count']}"}

    client_module.TikhubClient._request = fake_request

    def fake_tool(self, name):
        return {"path": f"/api/v1/test/{name}", "method": "GET",
                "queryParameters": [], "pathParameters": []}

    client_module.TikhubClient._tool = fake_tool
    return client_module.TikhubClient(platform="xiaohongshu"), calls


def test_call_caches_response_for_24h(tmp_path):
    mod = load_client()
    client, calls = _client_with_fake_request(mod, tmp_path)

    first = client.call("search", {"kw": "低卡便当"})
    second = client.call("search", {"kw": "低卡便当"})

    assert first == second
    assert calls["count"] == 1  # 第二次走缓存，不再打 API
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_cache_keyed_by_arguments(tmp_path):
    mod = load_client()
    client, calls = _client_with_fake_request(mod, tmp_path)

    client.call("search", {"kw": "a"})
    client.call("search", {"kw": "b"})

    assert calls["count"] == 2  # 不同参数不共享缓存


def test_cache_disabled_bypasses(tmp_path):
    mod = load_client()
    client, calls = _client_with_fake_request(mod, tmp_path)
    mod.set_cache_enabled(False)

    client.call("search", {"kw": "a"})
    client.call("search", {"kw": "a"})

    assert calls["count"] == 2
    mod.set_cache_enabled(True)  # 还原，避免影响其他用例


def test_expired_cache_entry_is_refetched(tmp_path):
    mod = load_client()
    client, calls = _client_with_fake_request(mod, tmp_path)

    client.call("search", {"kw": "a"})
    # 把缓存时间改成过期
    for entry in (tmp_path / "cache").glob("*.json"):
        data = json.loads(entry.read_text(encoding="utf-8"))
        data["cached_at"] = -1  # epoch 0 → 远超 TTL
        entry.write_text(json.dumps(data), encoding="utf-8")

    client.call("search", {"kw": "a"})
    assert calls["count"] == 2


def test_corrupt_cache_entry_falls_through(tmp_path):
    mod = load_client()
    client, calls = _client_with_fake_request(mod, tmp_path)

    client.call("search", {"kw": "a"})
    for entry in (tmp_path / "cache").glob("*.json"):
        entry.write_text("{not json", encoding="utf-8")

    result = client.call("search", {"kw": "a"})
    assert calls["count"] == 2
    assert result == {"data": "resp-2"}  # 缓存坏了不影响拿到新结果
