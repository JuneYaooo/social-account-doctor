import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "mc"


def load_mc_client():
    path = REPO_ROOT / "mediacrawler" / "lib" / "mc_client.py"
    spec = importlib.util.spec_from_file_location("mc_client_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mc = load_mc_client()


@pytest.fixture(autouse=True)
def _isolate_mc_state(tmp_path, monkeypatch):
    """锁和冷却标记是全机状态（默认在 skill 安装目录），测试必须拦到临时目录，
    否则会写到真实安装里（历史上真的发生过：一次跑测试把 MediaCrawler 拉起来）。"""
    monkeypatch.setattr(mc, "STATE_DIR", tmp_path / "mc-state")
    monkeypatch.setattr(mc, "LEGACY_DATA_DIR", tmp_path / "legacy-mc-data")


# ---------------------------------------------------------------------------
# platform mapping
# ---------------------------------------------------------------------------

def test_normalize_platform_maps_skill_names():
    assert mc.normalize_platform("xiaohongshu") == "xhs"
    assert mc.normalize_platform("douyin") == "dy"
    assert mc.normalize_platform("kuaishou") == "ks"
    assert mc.normalize_platform("bilibili") == "bili"


def test_normalize_platform_accepts_native_names():
    assert mc.normalize_platform("XHS") == "xhs"
    assert mc.normalize_platform("dy") == "dy"


def test_normalize_platform_rejects_wechat():
    with pytest.raises(mc.McError, match="视频号"):
        mc.normalize_platform("wechat")


# ---------------------------------------------------------------------------
# command building
# ---------------------------------------------------------------------------

def test_build_args_search():
    args = mc.build_crawler_args(
        "search", "xhs", keywords="低卡便当,减脂餐",
        out_dir="/tmp/mc-out",
    )
    joined = " ".join(args)
    assert "--platform xhs" in joined
    assert "--type search" in joined
    assert "--lt qrcode" in joined
    assert "--keywords 低卡便当,减脂餐" in joined
    assert "--save_data_option json" in joined
    assert "--save_data_path /tmp/mc-out" in joined
    assert "--get_comment true" in joined
    assert "--headless false" in joined


def test_build_args_detail_uses_specified_id():
    args = mc.build_crawler_args(
        "detail", "dy", ids=["https://v.douyin.com/abc/", "7428000000000001234"],
        comments=False, out_dir="/tmp/mc-out",
    )
    joined = " ".join(args)
    assert "--type detail" in joined
    assert "--specified_id https://v.douyin.com/abc/,7428000000000001234" in joined
    assert "--get_comment false" in joined


def test_build_args_creator_uses_creator_id():
    args = mc.build_crawler_args(
        "creator", "xhs", ids=["https://www.xiaohongshu.com/user/profile/5e7fabc"],
        out_dir="/tmp/mc-out",
    )
    joined = " ".join(args)
    assert "--type creator" in joined
    assert "--creator_id" in joined


def test_build_args_cookie_login_and_headless():
    args = mc.build_crawler_args(
        "search", "xhs", keywords="测试", login="cookie", cookies="web_session=abc",
        headless=True, out_dir="/tmp/mc-out",
    )
    joined = " ".join(args)
    assert "--lt cookie" in joined
    assert "--cookies web_session=abc" in joined
    assert "--headless true" in joined


def test_build_args_validation():
    with pytest.raises(mc.McError):
        mc.build_crawler_args("search", "xhs", keywords="  ")  # search 无关键词
    with pytest.raises(mc.McError):
        mc.build_crawler_args("detail", "xhs", ids=[])  # detail 无 id
    with pytest.raises(mc.McError):
        mc.build_crawler_args("search", "xhs", keywords="x", login="cookie")  # cookie 登录缺串
    with pytest.raises(mc.McError):
        mc.build_crawler_args("crawl", "xhs", keywords="x")  # 未知模式


# ---------------------------------------------------------------------------
# config patch
# ---------------------------------------------------------------------------

def test_patch_config_is_idempotent(tmp_path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg = cfg_dir / "base_config.py"
    cfg.write_text("HEADLESS = False\nENABLE_CDP_MODE = True\n", encoding="utf-8")
    assert mc.patch_config(tmp_path) is True
    assert "ENABLE_CDP_MODE = False" in cfg.read_text(encoding="utf-8")
    # second run: no change needed
    assert mc.patch_config(tmp_path) is False


# ---------------------------------------------------------------------------
# field normalization
# ---------------------------------------------------------------------------

def test_to_int_and_norm_ts():
    assert mc._to_int("1234") == 1234
    assert mc._to_int("") is None
    assert mc._to_int(None) is None
    assert mc._to_int("abc") is None
    # 平台中文数量级字符串（小红书搜索结果真实形态）
    assert mc._to_int("10万+") == 100000
    assert mc._to_int("9.3万") == 93000
    assert mc._to_int("1.2亿") == 120000000
    assert mc._to_int("1,234") == 1234
    assert mc._to_int("5.6W") == 56000
    # milliseconds get normalized to seconds
    assert mc._norm_ts(1758002400000) == 1758002400
    # plain seconds stay
    assert mc._norm_ts(1758002400) == 1758002400
    assert mc._norm_ts(0) is None


def test_parse_xhs_search_results_with_comments():
    result = mc.parse_results("search", "xhs", out_dir=FIXTURES)
    assert result["ok"] is True
    assert result["count"] == 2
    video = result["items"][0]
    assert video["id"] == "661f2b44000000001e021234"
    assert video["liked_count"] == 1234
    assert video["publish_time"] == 1758002400  # ms → s
    assert len(video["image_urls"]) == 2
    assert video["cover_url"].startswith("http://sns-img")
    assert video["tags"] == ["低卡便当", "减脂餐", "上班族"]
    assert video["xsec_token"] == "ABtoken1"
    assert "xsec_token=ABtoken1" in video["url"]
    # comments grouped onto their note
    assert len(video["comments"]) == 2
    assert video["comments"][0]["content"] == "跟着做了一周，真的瘦了"
    assert video["comments"][0]["like_count"] == 23
    assert video["comments"][0]["create_time"] == 1758002500
    # second note has no comments
    assert result["items"][1]["comments"] == []
    assert result["items"][1]["video_url"] is None
    assert result["items"][1]["type"] == "note"


def test_parse_douyin_detail_results():
    result = mc.parse_results("detail", "dy", out_dir=FIXTURES)
    assert result["ok"] is True
    item = result["items"][0]
    assert item["id"] == "7428000000000001234"
    assert item["liked_count"] == 23000
    assert item["publish_time"] == 1758002400  # already seconds
    assert item["video_url"].startswith("https://v26-web")
    assert item["cover_url"].startswith("https://p3-sign")
    assert item["comments"][0]["content"] == "链接蹲一个"
    assert item["comments"][0]["sub_comment_count"] == 3


def test_parse_kuaishou_search_results():
    result = mc.parse_results("search", "ks", out_dir=FIXTURES)
    item = result["items"][0]
    assert item["id"] == "3xkuaishou001"
    assert item["liked_count"] == 9876
    assert item["view_count"] == 152000
    assert item["collected_count"] is None  # ks 搜索结果不提供收藏数
    assert item["video_url"].startswith("https://play.kuaishou.com")
    assert item["publish_time"] == 1758002400  # ms → s


def test_parse_bilibili_creator_results():
    result = mc.parse_results("creator", "bili", out_dir=FIXTURES)
    item = result["items"][0]
    assert item["id"] == "1200000000000001"
    assert item["collected_count"] == 28000
    assert item["comment_count"] == 1500
    assert item["coin_count"] == 12000
    assert item["danmaku_count"] == 890
    assert item["view_count"] == 512000


def test_parse_results_dedupes_by_id(tmp_path):
    base = tmp_path / "xhs" / "json"
    base.mkdir(parents=True)
    row = {"note_id": "dup1", "title": "t", "liked_count": "1", "image_list": "", "time": 0, "note_url": ""}
    (base / "search_contents_2026-09-16.json").write_text(
        json.dumps([row, row]), encoding="utf-8")
    result = mc.parse_results("search", "xhs", out_dir=tmp_path)
    assert result["count"] == 1


def test_parse_results_no_output_is_structured(tmp_path):
    result = mc.parse_results("search", "xhs", out_dir=tmp_path)
    assert result["ok"] is False
    assert result["error"] == "no_output"
    assert result["items"] == []
    assert "hint" in result


# ---------------------------------------------------------------------------
# same-platform cooldown (account safety / rate control)
# ---------------------------------------------------------------------------

def test_cooldown_blocks_rapid_same_platform_crawl(monkeypatch, tmp_path):
    # no marker → allowed
    mc._check_cooldown("xhs")
    # fresh marker → rejected
    mc._mark_cooldown("xhs")
    with pytest.raises(mc.McError, match="冷却|间隔"):
        mc._check_cooldown("xhs")
    # other platforms unaffected
    mc._check_cooldown("dy")


def test_cooldown_expires(tmp_path):
    stale = mc.STATE_DIR / ".last-run-xhs"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text(str(1.0), encoding="utf-8")  # epoch → long past
    mc._check_cooldown("xhs")


def test_cooldown_corrupt_marker_is_ignored(tmp_path):
    mc.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (mc.STATE_DIR / ".last-run-ks").write_text("not-a-number", encoding="utf-8")
    mc._check_cooldown("ks")


def test_cooldown_reads_legacy_vendor_markers(tmp_path):
    """升级兼容：旧 vendor/mc-data 里的冷却标记仍会被读到，不会漏放一次抓取。"""
    legacy = mc.LEGACY_DATA_DIR / ".last-run-xhs"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(str(time.time() + 999_999), encoding="utf-8")  # 很久之后到期
    with pytest.raises(mc.McError, match="冷却"):
        mc._check_cooldown("xhs")


def test_cooldown_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "COOLDOWN_SECONDS", 1)
    mc._mark_cooldown("xhs")
    import time as _time
    _time.sleep(1.1)
    mc._check_cooldown("xhs")  # expired after 1s → allowed


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_reports_uninstalled(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "VENDOR_DIR", tmp_path / "vendor")
    monkeypatch.setattr(mc, "MC_DIR", tmp_path / "vendor" / "MediaCrawler")
    monkeypatch.setattr(mc, "VENV_DIR", tmp_path / "vendor" / "mc-venv")
    info = mc.status()
    assert info["ok"] is False
    assert info["cloned"] is False
    assert info["venv_ready"] is False
    assert info["login_state_platforms"] == []


def test_status_reports_login_state(monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    mc_dir = vendor / "MediaCrawler"
    (mc_dir / "browser_data").mkdir(parents=True)
    (mc_dir / "main.py").write_text("# main", encoding="utf-8")
    (mc_dir / "config").mkdir()
    (mc_dir / "config" / "base_config.py").write_text(
        "ENABLE_CDP_MODE = False\n", encoding="utf-8")
    (mc_dir / "browser_data" / "xhs_user_data_dir").mkdir()
    venv_bin = vendor / "mc-venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text("# fake", encoding="utf-8")

    monkeypatch.setattr(mc, "VENDOR_DIR", vendor)
    monkeypatch.setattr(mc, "MC_DIR", mc_dir)
    monkeypatch.setattr(mc, "VENV_DIR", vendor / "mc-venv")
    info = mc.status()
    assert info["cloned"] is True
    assert info["config_patched"] is True
    assert info["ok"] is True
    assert info["login_state_platforms"] == ["xhs"]


def test_find_python_returns_310_plus():
    import subprocess

    py = mc.find_python()
    if py is None:
        pytest.skip("no Python >= 3.10 found on this machine")
    out = subprocess.run(
        [str(py), "-c", "import sys; print(sys.version_info[:2])"],
        capture_output=True, text=True, timeout=15,
    )
    assert out.returncode == 0
    major, minor = json.loads(out.stdout.strip().replace("(", "[").replace(")", "]"))
    assert (major, minor) >= (3, 10)


# ---------------------------------------------------------------------------
# setup download-source selection (probes monkeypatched — no network)
# ---------------------------------------------------------------------------

def _clear_mirror_env(monkeypatch):
    for var in ("PIP_INDEX_URL", "PIP_INDEX", "PLAYWRIGHT_DOWNLOAD_HOST", "MC_GIT_URL", "MC_NO_MIRROR"):
        monkeypatch.delenv(var, raising=False)


def test_pip_index_respects_user_env(monkeypatch):
    monkeypatch.setenv("PIP_INDEX_URL", "https://example.com/simple")
    args, label = mc.pip_index_args(log=lambda m: None)
    assert args == []
    assert label == "env"


def test_pip_index_picks_fastest_mirror(monkeypatch):
    _clear_mirror_env(monkeypatch)
    speeds = {
        "https://pypi.org/simple": 800.0,
        "https://pypi.tuna.tsinghua.edu.cn/simple": 50.0,
        "https://mirrors.aliyun.com/pypi/simple": 60.0,
    }
    monkeypatch.setattr(mc, "_probe_ms", lambda url, timeout=4.0: speeds[url])
    args, label = mc.pip_index_args(log=lambda m: None)
    assert args == ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
    assert label == "清华 PyPI 镜像"


def test_pip_index_prefers_official_when_fastest(monkeypatch):
    _clear_mirror_env(monkeypatch)
    speeds = {
        "https://pypi.org/simple": 40.0,
        "https://pypi.tuna.tsinghua.edu.cn/simple": 500.0,
        "https://mirrors.aliyun.com/pypi/simple": 600.0,
    }
    monkeypatch.setattr(mc, "_probe_ms", lambda url, timeout=4.0: speeds[url])
    args, label = mc.pip_index_args(log=lambda m: None)
    assert args == []
    assert label == "官方 PyPI"


def test_pip_index_all_unreachable_falls_back_to_default(monkeypatch):
    _clear_mirror_env(monkeypatch)
    monkeypatch.setattr(mc, "_probe_ms", lambda url, timeout=4.0: None)
    args, label = mc.pip_index_args(log=lambda m: None)
    assert args == []
    assert label == "default"


def test_pip_index_disabled_by_no_mirror_env(monkeypatch):
    _clear_mirror_env(monkeypatch)
    monkeypatch.setenv("MC_NO_MIRROR", "1")
    assert mc.pip_index_args(log=lambda m: None) == ([], "direct")


def test_playwright_mirror_only_when_clearly_faster(monkeypatch):
    _clear_mirror_env(monkeypatch)
    speeds = {mc.PLAYWRIGHT_OFFICIAL_HOST: 500.0, mc.PLAYWRIGHT_MIRROR_HOST: 400.0}
    monkeypatch.setattr(mc, "_probe_ms", lambda url, timeout=4.0: speeds[url])
    # 快 20% 不够，必须显著快（2 倍）才切镜像
    assert mc.playwright_mirror_env(log=lambda m: None) == {}
    speeds[mc.PLAYWRIGHT_MIRROR_HOST] = 100.0
    assert mc.playwright_mirror_env(log=lambda m: None) == {
        "PLAYWRIGHT_DOWNLOAD_HOST": mc.PLAYWRIGHT_MIRROR_HOST
    }


def test_playwright_mirror_used_when_official_unreachable(monkeypatch):
    _clear_mirror_env(monkeypatch)
    speeds = {mc.PLAYWRIGHT_OFFICIAL_HOST: None, mc.PLAYWRIGHT_MIRROR_HOST: 300.0}
    monkeypatch.setattr(mc, "_probe_ms", lambda url, timeout=4.0: speeds[url])
    env = mc.playwright_mirror_env(log=lambda m: None)
    assert env["PLAYWRIGHT_DOWNLOAD_HOST"] == mc.PLAYWRIGHT_MIRROR_HOST


def test_playwright_mirror_respects_user_env(monkeypatch):
    _clear_mirror_env(monkeypatch)
    monkeypatch.setenv("PLAYWRIGHT_DOWNLOAD_HOST", "https://my-host.example")
    assert mc.playwright_mirror_env(log=lambda m: None) == {}


def test_clone_candidates_env_url_wins(monkeypatch):
    _clear_mirror_env(monkeypatch)
    monkeypatch.setenv("MC_GIT_URL", "https://mirror.example/MediaCrawler.git")
    assert mc.clone_url_candidates(log=lambda m: None) == [
        ("https://mirror.example/MediaCrawler.git", "MC_GIT_URL")
    ]


def test_clone_candidates_direct_first_when_github_reachable(monkeypatch):
    _clear_mirror_env(monkeypatch)
    probes = {"https://github.com": 300.0}
    monkeypatch.setattr(mc, "_probe_ms", lambda url, timeout=4.0: probes.get(url))
    plan = mc.clone_url_candidates(log=lambda m: None)
    assert plan[0] == (mc.MC_GIT_URL, "github 直连")
    assert len(plan) == 3  # 直连 + 两个 gh 代理垫后


def test_clone_candidates_mirrors_first_when_github_down(monkeypatch):
    _clear_mirror_env(monkeypatch)
    probes = {"https://github.com": None}
    monkeypatch.setattr(mc, "_probe_ms", lambda url, timeout=4.0: probes.get(url))
    plan = mc.clone_url_candidates(log=lambda m: None)
    assert len(plan) == 3
    assert plan[-1] == (mc.MC_GIT_URL, "github 直连")
    assert plan[0][1].startswith("gh 代理")


def test_clone_candidates_no_mirror_env(monkeypatch):
    _clear_mirror_env(monkeypatch)
    monkeypatch.setenv("MC_NO_MIRROR", "1")
    assert mc.clone_url_candidates(log=lambda m: None) == [(mc.MC_GIT_URL, "github 直连")]


def test_run_stream_captures_tail_and_exit_code():
    rc, tail = mc._run_stream(["sh", "-c", "echo line1; echo line2; exit 3"], log=lambda m: None, timeout=30)
    assert rc == 3
    assert tail[-2:] == ["line1", "line2"]


# ---------------------------------------------------------------------------
# crawl-level rate-control policy (comment defaults / volume caps / cooldown)
# ---------------------------------------------------------------------------

def _capture_crawl_args(monkeypatch, tmp_path):
    """Wire crawl() to a fake runner so we can assert the args it would send."""
    captured = {}

    def fake_run(args, timeout=900, log=None):
        captured["args"] = args
        return {"returncode": 0, "timed_out": False, "elapsed_seconds": 0.1}

    def fake_parse(mode, p, out_dir=None, since=None):
        captured.setdefault("since", since)
        return {"ok": True, "count": 1, "items": [{"id": "x"}]}

    monkeypatch.setattr(mc, "run_crawl", fake_run)
    monkeypatch.setattr(mc, "parse_results", fake_parse)
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    return captured


def test_crawl_search_defaults_comments_off(monkeypatch, tmp_path):
    """find（search）不消费评论内容 —— 默认不翻评论页，省掉单次 run 约 2/3 的请求。"""
    captured = _capture_crawl_args(monkeypatch, tmp_path)
    mc.crawl("search", "xhs", keywords="测试", log=lambda m: None)
    assert "--get_comment false" in " ".join(captured["args"])


def test_crawl_detail_and_creator_default_comments_on(monkeypatch, tmp_path):
    captured = _capture_crawl_args(monkeypatch, tmp_path)
    mc.crawl("detail", "xhs", ids=["http://x/1"], log=lambda m: None)
    assert "--get_comment true" in " ".join(captured["args"])
    # 换平台测 creator：同平台连跑会撞 30 分钟冷却（这正是冷却该拦的场景）
    mc.crawl("creator", "douyin", ids=["http://x/user/1"], log=lambda m: None)
    assert "--get_comment true" in " ".join(captured["args"])


def test_crawl_explicit_comments_overrides_mode_default(monkeypatch, tmp_path):
    captured = _capture_crawl_args(monkeypatch, tmp_path)
    mc.crawl("search", "xhs", keywords="测试", comments=True, log=lambda m: None)
    assert "--get_comment true" in " ".join(captured["args"])


def test_crawl_comment_cap_defaults_to_upstream_ten(monkeypatch, tmp_path):
    captured = _capture_crawl_args(monkeypatch, tmp_path)
    mc.crawl("detail", "xhs", ids=["http://x/1"], log=lambda m: None)
    assert "--max_comments_count_singlenotes 10" in " ".join(captured["args"])


def test_crawl_max_comments_propagates(monkeypatch, tmp_path):
    captured = _capture_crawl_args(monkeypatch, tmp_path)
    mc.crawl("detail", "xhs", ids=["http://x/1"], max_comments=5, log=lambda m: None)
    assert "--max_comments_count_singlenotes 5" in " ".join(captured["args"])


def test_cooldown_default_is_thirty_minutes(monkeypatch):
    monkeypatch.delenv("MC_COOLDOWN_SECONDS", raising=False)
    fresh = load_mc_client()
    assert fresh.COOLDOWN_SECONDS == 1800


# ---------------------------------------------------------------------------
# failure backoff: a run that launched the browser must cool down even on failure
# ---------------------------------------------------------------------------

def test_crawl_marks_failure_backoff_when_no_data(monkeypatch, tmp_path):
    """失败（未产出数据）也要退避——防止 agent 在风控敏感期零间隔循环重试。"""
    monkeypatch.setattr(mc, "run_crawl",
                        lambda args, timeout=900, log=None:
                        {"returncode": 2, "timed_out": False, "elapsed_seconds": 5.0})
    monkeypatch.setattr(mc, "parse_results",
                        lambda mode, p, out_dir=None, since=None:
                        {"ok": False, "error": "no_output", "count": 0, "items": []})
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    result = mc.crawl("search", "xhs", keywords="t", log=lambda m: None)
    assert result["ok"] is False
    assert result["error"] == "no_output"
    expiry = mc._cooldown_expiry("xhs")
    assert expiry is not None
    assert 500 < expiry - time.time() < 700  # ~10 分钟失败退避
    with pytest.raises(mc.McError, match="冷却"):
        mc._check_cooldown("xhs")


def test_crawl_reports_stale_when_run_wrote_nothing(monkeypatch, tmp_path):
    """本次没产出新文件时不能把历史文件当本次结果静默返回。"""
    base = tmp_path / "dy" / "json"
    base.mkdir(parents=True)
    old_file = base / "detail_contents_2026-09-01.json"
    old_file.write_text(json.dumps([{"aweme_id": "old1", "title": "t"}]), encoding="utf-8")
    day_ago = time.time() - 86400
    os.utime(old_file, (day_ago, day_ago))
    monkeypatch.setattr(mc, "run_crawl",
                        lambda args, timeout=900, log=None:
                        {"returncode": 0, "timed_out": False, "elapsed_seconds": 5.0})
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)

    result = mc.crawl("detail", "douyin", ids=["http://x/1"], log=lambda m: None)

    assert result["ok"] is False
    assert result["error"] == "stale_data"
    assert result["count"] == 0
    assert result["stale_files"][0]["age_minutes"] > 1000
    assert mc._cooldown_expiry("dy") is not None  # 失败退避生效
    assert not (mc.STATE_DIR / "crawl.lock").exists()  # 锁已释放


def test_parse_results_since_filters_stale_files(tmp_path):
    base = tmp_path / "xhs" / "json"
    base.mkdir(parents=True)
    old_file = base / "search_contents_2026-09-18.json"
    old_file.write_text(json.dumps([{"note_id": "s1", "title": "t", "liked_count": "1"}]),
                        encoding="utf-8")
    hour_ago = time.time() - 3600
    os.utime(old_file, (hour_ago, hour_ago))

    result = mc.parse_results("search", "xhs", out_dir=tmp_path, since=time.time())
    assert result["ok"] is False
    assert result["error"] == "stale_data"

    # 复用历史数据的路径（不传 since）不受影响
    assert mc.parse_results("search", "xhs", out_dir=tmp_path)["ok"] is True


def test_parse_results_accepts_files_written_after_since(tmp_path):
    base = tmp_path / "xhs" / "json"
    base.mkdir(parents=True)
    fresh_file = base / "search_contents_2026-09-18.json"
    fresh_file.write_text(json.dumps([{"note_id": "s1", "title": "t", "liked_count": "1"}]),
                          encoding="utf-8")
    result = mc.parse_results("search", "xhs", out_dir=tmp_path, since=time.time() - 60)
    assert result["ok"] is True
    assert result["count"] == 1


# ---------------------------------------------------------------------------
# global single-instance crawl lock (no concurrent crawls, ever)
# ---------------------------------------------------------------------------

def test_crawl_rejects_concurrent_run(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    mc.STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = mc.STATE_DIR / "crawl.lock"
    lock.write_text("999999 123", encoding="utf-8")
    with pytest.raises(mc.McError, match="另一个|并行"):
        mc.crawl("search", "xhs", keywords="t", log=lambda m: None)


def test_global_lock_blocks_other_platforms_too(monkeypatch, tmp_path):
    """跨平台并行同样拒绝——全机同一时间只允许一个抓取进程。"""
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    mc.STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = mc.STATE_DIR / "crawl.lock"
    lock.write_text("999999 123", encoding="utf-8")
    with pytest.raises(mc.McError, match="单实例|并行"):
        mc.crawl("detail", "bilibili", ids=["http://x/1"], log=lambda m: None)


def test_crawl_lock_released_after_run(monkeypatch, tmp_path):
    _capture_crawl_args(monkeypatch, tmp_path)
    mc.crawl("search", "dy", keywords="t", log=lambda m: None)
    assert not (mc.STATE_DIR / "crawl.lock").exists()


def test_crawl_steals_stale_lock(tmp_path, monkeypatch):
    """崩溃残留的陈旧锁可被抢占，不会把用户永久卡死。"""
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    mc.STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = mc.STATE_DIR / "crawl.lock"
    lock.write_text("999999 123", encoding="utf-8")
    stale = time.time() - mc.CRAWL_LOCK_STALE_SECONDS - 60
    os.utime(lock, (stale, stale))
    assert mc._acquire_crawl_lock() is not None


# ---------------------------------------------------------------------------
# per-run volume caps (enforced, not just guidance)
# ---------------------------------------------------------------------------

def test_volume_cap_rejects_too_many_keywords(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    with pytest.raises(mc.McError, match="关键词"):
        mc.crawl("search", "xhs", keywords="a,b,c,d", log=lambda m: None)


def test_volume_cap_rejects_too_many_detail_ids(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    ids = [f"http://x/{i}" for i in range(6)]
    with pytest.raises(mc.McError, match="detail"):
        mc.crawl("detail", "xhs", ids=ids, log=lambda m: None)


def test_volume_cap_rejects_too_many_creators(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    ids = [f"http://x/u/{i}" for i in range(3)]
    with pytest.raises(mc.McError, match="creator"):
        mc.crawl("creator", "xhs", ids=ids, log=lambda m: None)


def test_volume_caps_within_limits_pass(monkeypatch, tmp_path):
    _capture_crawl_args(monkeypatch, tmp_path)
    mc.crawl("search", "xhs", keywords="a,b,c", log=lambda m: None)  # 3 词 = 上限，放行
    mc.crawl("detail", "dy", ids=[f"http://x/{i}" for i in range(5)], log=lambda m: None)


# ---------------------------------------------------------------------------
# pacing jitter patch (fixed intervals are a classic bot fingerprint)
# ---------------------------------------------------------------------------

def _fake_mc_dir(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "base_config.py").write_text(
        "CRAWLER_MAX_SLEEP_SEC = 2\n", encoding="utf-8")
    core = tmp_path / "media_platform" / "xhs" / "core.py"
    core.parent.mkdir(parents=True)
    return core


def test_patch_pacing_applies_jitter_and_bumps_base_sleep(tmp_path):
    core = _fake_mc_dir(tmp_path)
    core.write_text(
        "import asyncio\nimport os\n\n"
        "await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)\n"
        "crawl_interval = config.CRAWLER_MAX_SLEEP_SEC\n",
        encoding="utf-8")

    result = mc.patch_pacing(tmp_path)

    assert result["base_sleep_3s"] is True
    text = core.read_text(encoding="utf-8")
    # bilibili core 原本没有 import random，补丁要补上
    assert "\nimport random\n" in text
    assert "asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC + random.uniform(0, config.CRAWLER_MAX_SLEEP_SEC))" in text
    assert "crawl_interval = config.CRAWLER_MAX_SLEEP_SEC + random.uniform" in text
    assert mc.pacing_patched(tmp_path) is True


def test_patch_pacing_is_idempotent(tmp_path):
    core = _fake_mc_dir(tmp_path)
    core.write_text(
        "import asyncio\nimport random\n\n"
        "await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)\n",
        encoding="utf-8")
    mc.patch_pacing(tmp_path)
    first = core.read_text(encoding="utf-8")
    mc.patch_pacing(tmp_path)
    second = core.read_text(encoding="utf-8")
    assert first == second  # 第二次不重复包一层
    assert first.count("import random") == 1


def test_patch_pacing_leaves_clean_files_alone(tmp_path):
    core = _fake_mc_dir(tmp_path)
    original = "import asyncio\nimport random\n\nprint('hi')\n"
    core.write_text(original, encoding="utf-8")
    mc.patch_pacing(tmp_path)
    assert core.read_text(encoding="utf-8") == original


def test_crawl_passes_since_to_parse(monkeypatch, tmp_path):
    captured = _capture_crawl_args(monkeypatch, tmp_path)
    before = time.time()
    mc.crawl("search", "xhs", keywords="t", log=lambda m: None)
    assert captured["since"] is not None
    assert captured["since"] >= before - 1


# ---------------------------------------------------------------------------
# cookie redaction in debug logs
# ---------------------------------------------------------------------------

def test_redact_cmd_masks_cookie_values():
    cmd = ["python", "main.py", "--cookies", "web_session=secret;", "--lt", "cookie"]
    assert "secret" not in mc._redact_cmd(cmd)
    assert "--cookies ***" in mc._redact_cmd(cmd)
    assert mc._redact_cmd(["--cookies=abc", "x"]) == "--cookies=*** x"


# ---------------------------------------------------------------------------
# run_crawl timeout enforcement
# ---------------------------------------------------------------------------

def test_run_crawl_kills_on_timeout(monkeypatch, tmp_path):
    """A crawler that hangs (e.g. nobody scans the QR) must be killed at timeout."""
    fake_venv = tmp_path / "fake-venv-python"
    fake_venv.write_text("#!/bin/sh\nsleep 60\n", encoding="utf-8")
    fake_venv.chmod(0o755)
    mc_dir = tmp_path / "MediaCrawler"
    mc_dir.mkdir()

    monkeypatch.setattr(mc, "venv_python", lambda: fake_venv)
    monkeypatch.setattr(mc, "MC_DIR", mc_dir)

    result = mc.run_crawl(["--type", "search"], timeout=4, log=lambda msg: None)
    assert result["timed_out"] is True
    assert result["elapsed_seconds"] < 30  # killed on time, not after sleep 60

    # the sleep child of the fake venv python must be gone
    import subprocess as sp
    pgrep = sp.run(["pgrep", "-f", "sleep 60"], capture_output=True, text=True)
    assert pgrep.returncode != 0


# ---------------------------------------------------------------------------
# pip install resilience (bulk failure -> per-package three-tier retry)
# ---------------------------------------------------------------------------

def _fake_pip_runner(monkeypatch, fail_bulk=True, always_fail=()):
    calls = []

    def fake_run_stream(cmd, log=None, timeout=1800, env=None, cwd=None, tail_lines=25):
        joined = " ".join(cmd)
        calls.append(joined)
        if fail_bulk and " -r " in joined:
            return 2, ["bulk install failed"]
        for bad in always_fail:
            if bad in joined:
                return 1, [f"{bad} failed"]
        return 0, ["ok"]

    monkeypatch.setattr(mc, "_run_stream", fake_run_stream)
    return calls


def test_parse_requirements_strips_comments_and_options(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text(
        "# header comment\n"
        "httpx==0.28.1\n"
        "\n"
        "aiofiles~=23.2.1  # inline comment\n"
        "-r other.txt\n"
        "--index-url https://example.com\n",
        encoding="utf-8",
    )
    assert mc._parse_requirements(req) == ["httpx==0.28.1", "aiofiles~=23.2.1"]


def test_pip_install_recovers_via_per_package_fallback(tmp_path, monkeypatch):
    """整体装失败时逐包救回，不再需要 agent 手动逐个处理。"""
    req = tmp_path / "requirements.txt"
    req.write_text("httpx==1.0\njieba==0.42.1\n", encoding="utf-8")
    calls = _fake_pip_runner(monkeypatch, fail_bulk=True)

    mc._pip_install(Path("/fake/venv/bin/python"), req, [], log=lambda m: None)  # 不抛

    assert " -r " in calls[0]  # 先尝试整体安装
    assert any("httpx==1.0" in c for c in calls)
    assert any("jieba==0.42.1" in c for c in calls)


def test_pip_install_escalates_retry_flags_for_stubborn_package(tmp_path, monkeypatch):
    """顽固包走完三级重试（默认→清缓存→关构建隔离），失败时精确点名并给手动命令。"""
    req = tmp_path / "requirements.txt"
    req.write_text("boom==1.0\n", encoding="utf-8")
    calls = _fake_pip_runner(monkeypatch, fail_bulk=True, always_fail=("boom==1.0",))

    with pytest.raises(mc.McError, match="boom==1.0"):
        mc._pip_install(Path("/fake/venv/bin/python"), req, [], log=lambda m: None)

    boom_calls = [c for c in calls if "boom==1.0" in c]
    assert len(boom_calls) == 3
    assert any("--no-cache-dir" in c for c in boom_calls)
    assert any("--no-build-isolation" in c for c in boom_calls)
    # 关构建隔离前先补齐 setuptools/wheel（Python 3.12 venv 不自带）
    assert any("setuptools" in c and "wheel" in c for c in calls)


def test_pip_install_bulk_success_skips_fallback(tmp_path, monkeypatch):
    req = tmp_path / "requirements.txt"
    req.write_text("httpx==1.0\n", encoding="utf-8")
    calls = _fake_pip_runner(monkeypatch, fail_bulk=False)

    mc._pip_install(Path("/fake/venv/bin/python"), req, [], log=lambda m: None)

    assert len(calls) == 1  # 整体一次成功，不进逐包流程


# ---------------------------------------------------------------------------
# optional wordcloud patch (drops wheel-less sdists from the critical path)
# ---------------------------------------------------------------------------

def _fake_words_py(tmp_path, content=None):
    words = tmp_path / "tools" / "words.py"
    words.parent.mkdir(parents=True)
    if content is None:
        content = (
            "import asyncio\nimport json\n\n"
            "import aiofiles\n"
            "import jieba\n"
            "import matplotlib.pyplot as plt\n"
            "from wordcloud import WordCloud\n\n"
            "import config\n\n\n"
            "class AsyncWordCloudGenerator:\n"
            "    def __init__(self):\n"
            "        logging.getLogger('jieba').setLevel(logging.WARNING)\n"
        )
    words.write_text(content, encoding="utf-8")
    return words


def test_patch_optional_wordcloud_wraps_imports_and_guards_init(tmp_path):
    words = _fake_words_py(tmp_path)
    assert mc.patch_optional_wordcloud(tmp_path) is True
    text = words.read_text(encoding="utf-8")
    assert "WORDCLOUD_DEPS_READY = True" in text
    assert "except ImportError" in text
    # 开词云但缺可选依赖时给明确报错，而不是 NameError
    assert "raise RuntimeError('词云功能需要可选依赖" in text
    # import 成功的分支里三件套仍然可见
    assert "    import jieba" in text


def test_patch_optional_wordcloud_is_idempotent(tmp_path):
    _fake_words_py(tmp_path)
    assert mc.patch_optional_wordcloud(tmp_path) is True
    first = (tmp_path / "tools" / "words.py").read_text(encoding="utf-8")
    assert mc.patch_optional_wordcloud(tmp_path) is False
    assert (tmp_path / "tools" / "words.py").read_text(encoding="utf-8") == first


def test_patch_optional_wordcloud_leaves_drifted_files_alone(tmp_path):
    _fake_words_py(tmp_path, content="import asyncio\nprint('upstream changed')\n")
    assert mc.patch_optional_wordcloud(tmp_path) is False
    assert (tmp_path / "tools" / "words.py").read_text(encoding="utf-8") == "import asyncio\nprint('upstream changed')\n"


# ---------------------------------------------------------------------------
# unified output-root conventions (./output/cache/mc-data under CWD)
# ---------------------------------------------------------------------------

def test_data_dir_defaults_to_unified_output_root(monkeypatch, tmp_path):
    monkeypatch.delenv("MC_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fresh = load_mc_client()
    assert fresh.DATA_DIR == tmp_path / "output" / "cache" / "mc-data"
    # 锁和冷却标记仍然在 skill 安装目录（全机状态，不跟项目目录走）
    assert fresh.STATE_DIR == fresh.VENDOR_DIR / "mc-state"


def test_data_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MC_DATA_DIR", str(tmp_path / "custom-data"))
    fresh = load_mc_client()
    assert fresh.DATA_DIR == tmp_path / "custom-data"
