import importlib.util
import json
import sys
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
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    # no marker → allowed
    mc._check_cooldown("xhs")
    # fresh marker → rejected
    mc._mark_cooldown("xhs")
    with pytest.raises(mc.McError, match="冷却|间隔"):
        mc._check_cooldown("xhs")
    # other platforms unaffected
    mc._check_cooldown("dy")


def test_cooldown_expires(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    stale = tmp_path / ".last-run-xhs"
    stale.write_text(str(1.0), encoding="utf-8")  # epoch → long past
    mc._check_cooldown("xhs")


def test_cooldown_corrupt_marker_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
    (tmp_path / ".last-run-ks").write_text("not-a-number", encoding="utf-8")
    mc._check_cooldown("ks")


def test_cooldown_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "DATA_DIR", tmp_path)
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
