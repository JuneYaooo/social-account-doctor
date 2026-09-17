"""MediaCrawler adapter — 用自己的账号登录抓平台数据，不需要 TikHub key.

把 NanmiCoder/MediaCrawler（Playwright 真实浏览器爬虫）包装成与本仓库
``tikhub`` CLI 同风格的本地数据源：

    mc search  --platform xiaohongshu --keywords "词1,词2"   # 关键词搜（find）
    mc detail  --platform douyin --ids "url1,url2"           # 作品详情（crack）
    mc creator --platform xhs --ids "profile_url"            # 创作者主页（账号诊断）

首次使用 ``mc --setup``：克隆 MediaCrawler 到 vendor/、建独立 venv、装
Playwright chromium，并把 ENABLE_CDP_MODE 补丁为 False（走标准 Playwright
模式，登录态落在 vendor/MediaCrawler/browser_data/，扫码一次长期复用）。

所有机器可读结果以 JSON 打到 stdout；人类可读进度走 stderr。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIR = Path(os.environ.get("MC_VENDOR_DIR", REPO_ROOT / "vendor"))
MC_DIR = VENDOR_DIR / "MediaCrawler"
VENV_DIR = VENDOR_DIR / "mc-venv"
DATA_DIR = VENDOR_DIR / "mc-data"
VERSION_FILE = VENDOR_DIR / "mc-version.txt"

MC_GIT_URL = "https://github.com/NanmiCoder/MediaCrawler.git"
# 适配此 adapter 时的上游 HEAD；setup 优先 fetch 这个 commit，失败则用默认分支
PINNED_COMMIT = "60e66f2a925816960bbd44af5d6c9b8385d79335"

# 同平台两次抓取的最小间隔（秒）。用户账号登录抓取，抓太密会触发平台风控。
# 合并关键词（--keywords "词1,词2"）和批量 ID（--ids "url1,url2"）一次跑完，
# 不要拆成多次调用绕冷却。用户明确要求时可用 --force 覆盖。
COOLDOWN_SECONDS = int(os.environ.get("MC_COOLDOWN_SECONDS", "300"))

# skill 平台名 → MediaCrawler --platform 值
PLATFORM_MAP = {
    "xiaohongshu": "xhs",
    "douyin": "dy",
    "kuaishou": "ks",
    "bilibili": "bili",
}
LOGIN_TYPES = ("qrcode", "phone", "cookie")
CRAWL_MODES = ("search", "detail", "creator")

# MediaCrawler 的 json 输出里作者身份是匿名哈希 + 脱敏昵称（防骚扰设计），
# 我们在结果里原样保留并向上层声明这一限制。
ANONYMIZED_FIELDS = ("creator_hash", "nickname")

DEBUG = os.environ.get("MC_DEBUG") == "1"


class McError(Exception):
    """Raised on setup, transport, or parse failures of the MediaCrawler path."""


def _debug(msg: str) -> None:
    if DEBUG:
        print(f"[mc] {msg}", file=sys.stderr)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# status / setup
# ---------------------------------------------------------------------------

def _python_search_paths() -> list[Path]:
    home = Path.home()
    roots = [
        home / "opt" / "miniconda3" / "bin",
        home / "opt" / "anaconda3" / "bin",
        home / "miniconda3" / "bin",
        home / "anaconda3" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ]
    out: list[Path] = []
    for root in roots:
        if root.is_dir():
            out.extend(sorted(root.glob("python3.*")))
            out.append(root / "python3")
    return out


def find_python() -> Path | None:
    """Find a Python >= 3.10 for the dedicated venv (MediaCrawler target 3.11)."""
    candidates: list[Path] = []
    env_bin = os.environ.get("MC_PYTHON")
    if env_bin:
        candidates.append(Path(env_bin))
    candidates.append(Path(sys.executable))
    for name in ("python3.12", "python3.11", "python3.13", "python3.10", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    candidates.extend(_python_search_paths())
    seen: set[str] = set()
    for py in candidates:
        key = str(py)
        if key in seen or not py.is_file():
            continue
        seen.add(key)
        try:
            out = subprocess.run(
                [str(py), "-c", "import sys; print(sys.version_info[:2])"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode != 0:
                continue
            major, minor = json.loads(out.stdout.strip().replace("(", "[").replace(")", "]"))
            if (major, minor) >= (3, 10):
                return py
        except (subprocess.TimeoutExpired, ValueError, OSError):
            continue
    return None


def venv_python() -> Path:
    suffix = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return VENV_DIR / suffix


def _read_version_file() -> dict:
    try:
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=600,
    )


def patch_config(mc_dir: Path | None = None) -> bool:
    """Disable CDP mode so runs use the bundled Playwright chromium.

    CDP 模式要求用户本机 Chrome >= 144 且手动开远程调试，自动化不可控；
    标准 Playwright 模式的登录态落在 browser_data/ 可长期复用。幂等。
    """
    mc_dir = mc_dir or MC_DIR
    path = mc_dir / "config" / "base_config.py"
    if not path.is_file():
        raise McError(f"config not found: {path}")
    text = path.read_text(encoding="utf-8")
    patched = text.replace("ENABLE_CDP_MODE = True", "ENABLE_CDP_MODE = False")
    changed = patched != text
    if changed:
        path.write_text(patched, encoding="utf-8")
    return changed


def login_state_platforms() -> list[str]:
    """Platforms that already have a saved login (browser_data profile dir)."""
    browser_data = MC_DIR / "browser_data"
    if not browser_data.is_dir():
        return []
    states = []
    for mc_plat in ("xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"):
        if any(browser_data.glob(f"{mc_plat}_user_data_dir*")):
            states.append(mc_plat)
    return states


def find_node() -> str | None:
    """Node.js >= 16 is required by MediaCrawler only for douyin signing."""
    return shutil.which("node")


def status() -> dict:
    node = find_node()
    info: dict[str, Any] = {
        "ok": False,
        "repo_root": str(REPO_ROOT),
        "vendor_dir": str(VENDOR_DIR),
        "mediacrawler_dir": str(MC_DIR),
        "cloned": (MC_DIR / "main.py").is_file(),
        "venv_ready": venv_python().is_file(),
        "config_patched": False,
        "login_state_platforms": login_state_platforms(),
        "node_found": node is not None,
        "node_path": node,
        "platforms": {
            "xiaohongshu": "xhs", "douyin": "dy", "kuaishou": "ks", "bilibili": "bili",
        },
        "unsupported_platforms": {
            "wechat": "视频号不支持 MediaCrawler 路径；用 TikHub（wechat_* 端点）或让用户上传本地视频",
        },
    }
    info["platform_notes"] = {
        "douyin": "需要本机 Node.js >= 16（签名用）；未检测到时抖音任务会失败，其余平台不受影响"
        if node is None else "ok",
    }
    if info["cloned"] and info["venv_ready"]:
        cfg = MC_DIR / "config" / "base_config.py"
        if cfg.is_file():
            info["config_patched"] = "ENABLE_CDP_MODE = False" in cfg.read_text(encoding="utf-8")
        info["ok"] = info["config_patched"]
    info["version"] = _read_version_file()
    return info


def setup(force: bool = False, log: Callable[[str], None] = _log) -> dict:
    """Clone MediaCrawler, build venv, install Playwright chromium, patch config."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    steps: dict[str, Any] = {}

    py = find_python()
    if py is None:
        raise McError(
            "需要 Python >= 3.10 来创建 MediaCrawler 虚拟环境；"
            "用 MC_PYTHON 环境变量指定解释器后重试"
        )
    steps["python"] = str(py)

    # 1. clone（GitHub 直连经常抖，带重试；失败清掉半成品目录）
    if (MC_DIR / "main.py").is_file() and not force:
        steps["clone"] = "skipped (already cloned)"
    else:
        if MC_DIR.exists():
            log(f"[mc] 移除已有目录 {MC_DIR}")
            shutil.rmtree(MC_DIR)
        last_err = ""
        cloned = False
        for attempt in range(1, 4):
            log(f"[mc] 克隆 MediaCrawler → {MC_DIR}（第 {attempt}/3 次）")
            result = _git(["clone", "--depth", "1", MC_GIT_URL, str(MC_DIR)])
            if result.returncode == 0:
                cloned = True
                break
            last_err = result.stderr.strip()[:300]
            if MC_DIR.exists():
                shutil.rmtree(MC_DIR, ignore_errors=True)
            time.sleep(2 * attempt)
        if not cloned:
            raise McError(
                f"git clone 失败（重试 3 次）: {last_err}。"
                "检查到 github.com 的网络；或手动克隆后放到 vendor/MediaCrawler 再重跑 mc --setup"
            )
        # pin 到适配时的 commit；HEAD 已是目标或上游漂移导致 fetch 失败则保留原样
        actual_sha = _git(["rev-parse", "HEAD"], cwd=MC_DIR).stdout.strip()
        if actual_sha != PINNED_COMMIT:
            pin = _git(["fetch", "--depth", "1", "origin", PINNED_COMMIT], cwd=MC_DIR)
            if pin.returncode == 0 and _git(["checkout", "--quiet", PINNED_COMMIT], cwd=MC_DIR).returncode == 0:
                steps["clone"] = f"pinned {PINNED_COMMIT[:12]}"
            else:
                steps["clone"] = "default branch (pin failed, upstream may have moved)"
        else:
            steps["clone"] = f"pinned {PINNED_COMMIT[:12]}"

    actual_sha = _git(["rev-parse", "HEAD"], cwd=MC_DIR).stdout.strip()

    # 2. venv
    if venv_python().is_file() and not force:
        steps["venv"] = "skipped (already exists)"
    else:
        log(f"[mc] 创建虚拟环境 → {VENV_DIR}")
        result = subprocess.run([str(py), "-m", "venv", str(VENV_DIR)], capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise McError(f"venv 创建失败: {result.stderr.strip()[:300]}")
        steps["venv"] = "created"

    # 3. deps
    vpy = venv_python()
    log("[mc] 安装 MediaCrawler 依赖（首次较慢，几分钟）")
    result = subprocess.run(
        [str(vpy), "-m", "pip", "install", "--timeout", "120", "-r", str(MC_DIR / "requirements.txt")],
        capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0:
        raise McError(f"pip install 失败: {result.stderr.strip()[-500:]}")
    steps["pip"] = "installed"

    # 4. playwright chromium
    log("[mc] 安装 Playwright chromium")
    result = subprocess.run(
        [str(vpy), "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True, timeout=1200,
    )
    if result.returncode != 0:
        raise McError(f"playwright install 失败: {result.stderr.strip()[-300:]}")
    steps["playwright"] = "chromium installed"

    # 5. patch config + 版本记录
    steps["config_patch"] = "applied" if patch_config() else "already patched"
    VERSION_FILE.write_text(json.dumps({
        "pinned_commit": PINNED_COMMIT,
        "actual_commit": actual_sha,
        "setup_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6. smoke test
    result = subprocess.run(
        [str(vpy), "main.py", "--help"], cwd=MC_DIR, capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise McError(f"main.py --help 自检失败: {result.stderr.strip()[:300]}")
    steps["smoke_test"] = "main.py --help OK"

    return {"ok": True, "steps": steps, "status": status()}


# ---------------------------------------------------------------------------
# command build / run
# ---------------------------------------------------------------------------

def normalize_platform(platform: str) -> str:
    p = platform.strip().lower()
    if p in PLATFORM_MAP:
        return PLATFORM_MAP[p]
    if p in PLATFORM_MAP.values():
        return p
    raise McError(
        f"平台 {platform!r} 不支持 MediaCrawler 路径。"
        f"支持: {', '.join(PLATFORM_MAP)}（视频号请走 TikHub 或本地视频）"
    )


def build_crawler_args(
    mode: str,
    platform_mc: str,
    keywords: str = "",
    ids: list[str] | None = None,
    max_notes: int = 20,
    start_page: int = 1,
    comments: bool = True,
    max_comments_per_note: int = 20,
    login: str = "qrcode",
    cookies: str = "",
    headless: bool = False,
    out_dir: Path | str | None = None,
) -> list[str]:
    """Build ``main.py`` CLI args; mirrors cmd_arg/arg.py of MediaCrawler."""
    if mode not in CRAWL_MODES:
        raise McError(f"未知模式 {mode!r}（支持 search/detail/creator）")
    if login not in LOGIN_TYPES:
        raise McError(f"未知登录方式 {login!r}（支持 {'/'.join(LOGIN_TYPES)}）")
    if login == "cookie" and not cookies:
        raise McError("cookie 登录需要 --cookies")
    if mode == "search" and not keywords.strip():
        raise McError("search 模式需要 --keywords（多个词用英文逗号分隔）")
    if mode in ("detail", "creator") and not ids:
        raise McError(f"{mode} 模式需要 --ids（支持完整链接或纯 ID，逗号分隔）")

    save_path = Path(out_dir) if out_dir else DATA_DIR
    args = [
        "--platform", platform_mc,
        "--lt", login,
        "--type", mode,
        "--start", str(max(1, start_page)),
        "--crawler_max_notes_count", str(max(1, max_notes)),
        "--get_comment", "true" if comments else "false",
        "--get_sub_comment", "false",
        "--max_comments_count_singlenotes", str(max(1, max_comments_per_note)),
        "--max_concurrency_num", "1",
        "--save_data_option", "json",
        "--save_data_path", str(save_path),
        "--headless", "true" if headless else "false",
    ]
    if keywords.strip():
        args += ["--keywords", keywords.strip()]
    if ids:
        args += ["--specified_id" if mode == "detail" else "--creator_id", ",".join(ids)]
    if cookies:
        args += ["--cookies", cookies]
    return args


def run_crawl(
    crawler_args: list[str],
    timeout: int = 900,
    log: Callable[[str], None] = _log,
) -> dict:
    """Run main.py in the MediaCrawler venv; stream stderr, enforce hard timeout.

    日志泵在独立线程里跑：MediaCrawler 卡住（比如没人扫码）时不输出新行，
    主线程的超时控制不能跟着阻塞。杀进程用进程组信号，连 Playwright 拉起的
    chromium 一起收掉。
    """
    if not venv_python().is_file():
        raise McError("MediaCrawler 未安装；先运行: mc --setup")
    cmd = [str(venv_python()), "main.py", *crawler_args]
    _debug(f"run: {' '.join(cmd)}")
    log("[mc] 启动 MediaCrawler（首次运行会弹出浏览器，请在窗口里扫码登录；登录态会保存，之后免扫码）")
    started = time.time()
    proc = subprocess.Popen(
        cmd, cwd=MC_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        start_new_session=True,
    )

    def _pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log(f"[MediaCrawler] {line}")

    pump = threading.Thread(target=_pump, daemon=True)
    pump.start()

    deadline = started + timeout
    while pump.is_alive() and time.time() < deadline:
        pump.join(timeout=1.0)
    timed_out = pump.is_alive()

    if timed_out:
        log(f"[mc] 超过 {timeout}s，终止爬取（已抓到的数据仍会解析）")
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=30)
        pump.join(timeout=5)
    else:
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            timed_out = True

    return {
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.time() - started, 1),
        "command": cmd,
    }


# ---------------------------------------------------------------------------
# result parsing → unified schema
# ---------------------------------------------------------------------------

def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace(",", "")
    try:
        return int(text)
    except ValueError:
        pass
    # 平台互动数常是 "10万+" / "9.3万" / "1.2亿" 这类中文数量级字符串
    match = re.fullmatch(r"([\d.]+)\s*(万|w|亿)?\+?", text, re.IGNORECASE)
    if match:
        number = float(match.group(1))
        unit = match.group(2)
        if unit:
            number *= 100_000_000 if unit.lower() == "亿" else 10_000
        return int(number)
    return None


def _norm_ts(value: Any) -> int | None:
    """Normalize to unix seconds; MediaCrawler mixes ms (xhs/ks) and s (dy/bili)."""
    ts = _to_int(value)
    if ts is None or ts <= 0:
        return None
    return ts // 1000 if ts > 10_000_000_000 else ts


def _split_csv(value: Any) -> list[str]:
    if not value:
        return []
    return [part for part in str(value).split(",") if part.strip()]


def _split_tags(value: Any) -> list[str]:
    if not value:
        return []
    return [part for part in str(value).split(",") if part.strip()]


def _first(*values: Any) -> Any:
    for v in values:
        if v not in (None, ""):
            return v
    return None


def _norm_item(platform_mc: str, raw: dict) -> dict:
    """Map MediaCrawler per-platform content fields onto the unified schema."""
    if platform_mc == "xhs":
        item = {
            "id": raw.get("note_id"),
            "url": raw.get("note_url"),
            "type": raw.get("type"),
            "title": raw.get("title"),
            "desc": raw.get("desc"),
            "publish_time": _norm_ts(raw.get("time")),
            "liked_count": _to_int(raw.get("liked_count")),
            "collected_count": _to_int(raw.get("collected_count")),
            "comment_count": _to_int(raw.get("comment_count")),
            "share_count": _to_int(raw.get("share_count")),
            "image_urls": _split_csv(raw.get("image_list")),
            "video_url": raw.get("video_url") or None,
            "cover_url": _first(*_split_csv(raw.get("image_list"))[:1]),
            "tags": _split_tags(raw.get("tag_list")),
            "keyword": raw.get("source_keyword"),
            "xsec_token": raw.get("xsec_token"),
        }
    elif platform_mc == "dy":
        item = {
            "id": raw.get("aweme_id"),
            "url": raw.get("aweme_url"),
            "type": "video",
            "title": raw.get("title"),
            "desc": raw.get("desc"),
            "publish_time": _norm_ts(raw.get("create_time")),
            "liked_count": _to_int(raw.get("liked_count")),
            "collected_count": _to_int(raw.get("collected_count")),
            "comment_count": _to_int(raw.get("comment_count")),
            "share_count": _to_int(raw.get("share_count")),
            "image_urls": _split_csv(raw.get("note_download_url")),
            "video_url": raw.get("video_download_url") or None,
            "cover_url": raw.get("cover_url") or None,
            "tags": [],
            "keyword": raw.get("source_keyword"),
        }
    elif platform_mc == "ks":
        item = {
            "id": raw.get("video_id"),
            "url": raw.get("video_url"),
            "type": "video",
            "title": raw.get("title"),
            "desc": raw.get("desc"),
            "publish_time": _norm_ts(raw.get("create_time")),
            "liked_count": _to_int(raw.get("liked_count")),
            "collected_count": None,  # 快手搜索结果不提供收藏/分享数
            "comment_count": None,
            "share_count": None,
            "view_count": _to_int(raw.get("viewd_count")),
            "image_urls": [],
            "video_url": raw.get("video_play_url") or None,
            "cover_url": raw.get("video_cover_url") or None,
            "tags": [],
            "keyword": raw.get("source_keyword"),
        }
    elif platform_mc == "bili":
        item = {
            "id": raw.get("video_id"),
            "url": raw.get("video_url"),
            "type": "video",
            "title": raw.get("title"),
            "desc": raw.get("desc"),
            "publish_time": _norm_ts(raw.get("create_time")),
            "liked_count": _to_int(raw.get("liked_count")),
            "collected_count": _to_int(raw.get("video_favorite_count")),
            "comment_count": _to_int(raw.get("video_comment")),
            "share_count": _to_int(raw.get("video_share_count")),
            "view_count": _to_int(raw.get("video_play_count")),
            "coin_count": _to_int(raw.get("video_coin_count")),
            "danmaku_count": _to_int(raw.get("video_danmaku")),
            "image_urls": [_first(raw.get("video_cover_url"))] if raw.get("video_cover_url") else [],
            "video_url": raw.get("video_url") or None,
            "cover_url": raw.get("video_cover_url") or None,
            "tags": [],
            "keyword": raw.get("source_keyword"),
        }
    else:  # pragma: no cover - defensive
        raise McError(f"no normalizer for platform {platform_mc!r}")
    item["nickname"] = raw.get("nickname")  # 已脱敏
    item["creator_hash"] = raw.get("creator_hash")
    return item


_COMMENT_LINK_KEYS = {"xhs": "note_id", "dy": "aweme_id", "ks": "video_id", "bili": "video_id"}


def _norm_comment(platform_mc: str, raw: dict) -> dict:
    return {
        "id": raw.get("comment_id"),
        "content": raw.get("content"),
        "like_count": _to_int(raw.get("like_count")),
        "create_time": _norm_ts(raw.get("create_time")),
        "sub_comment_count": _to_int(raw.get("sub_comment_count")),
        "nickname": raw.get("nickname"),  # 已脱敏
    }


def _load_json_file(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _debug(f"skip unreadable result file {path}: {exc}")
        return []
    if isinstance(data, dict):
        data = [data]
    return [row for row in data if isinstance(row, dict)]


def _latest_files(directory: Path, pattern: str, keep: int = 1) -> list[Path]:
    """Newest-first result files; keep>1 merges recent runs of the same day."""
    if not directory.is_dir():
        return []
    files = [p for p in directory.glob(pattern) if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:keep]


def parse_results(mode: str, platform_mc: str, out_dir: Path | str | None = None) -> dict:
    """Read MediaCrawler JSON output and normalize it for the analysis pipeline."""
    if mode not in CRAWL_MODES:
        raise McError(f"未知模式 {mode!r}")
    base = (Path(out_dir) if out_dir else DATA_DIR) / platform_mc / "json"
    content_files = _latest_files(base, f"{mode}_contents_*.json")
    comment_files = _latest_files(base, f"{mode}_comments_*.json", keep=3)
    if not content_files:
        return {
            "ok": False,
            "error": "no_output",
            "platform": platform_mc,
            "mode": mode,
            "items": [],
            "count": 0,
            "searched_dirs": [str(base)],
            "hint": "没有找到 MediaCrawler 输出；检查上方日志（常见原因：未扫码登录 / 触发风控 / 关键词无结果）",
        }

    comments_by_id: dict[str, list[dict]] = {}
    seen_comment_ids: set[str] = set()
    for cf in comment_files:
        for raw in _load_json_file(cf):
            linked = raw.get(_COMMENT_LINK_KEYS.get(platform_mc, ""))
            if not linked:
                continue
            cid = str(raw.get("comment_id"))
            if cid in seen_comment_ids:
                continue
            seen_comment_ids.add(cid)
            comments_by_id.setdefault(str(linked), []).append(_norm_comment(platform_mc, raw))

    items = []
    for pf in content_files:
        for raw in _load_json_file(pf):
            item = _norm_item(platform_mc, raw)
            if not item.get("id"):
                continue
            item["comments"] = comments_by_id.get(str(item["id"]), [])
            items.append(item)

    # dedupe (multi-keyword runs and re-runs share the per-day output file)
    seen: set[str] = set()
    unique = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        unique.append(item)

    return {
        "ok": True,
        "platform": platform_mc,
        "mode": mode,
        "count": len(unique),
        "items": unique,
        "raw_files": [str(p) for p in content_files + comment_files],
        "note": "nickname 为脱敏值、creator_hash 为匿名哈希（MediaCrawler 防骚扰设计），不要写进对外报告",
    }


def _cooldown_file(platform_mc: str) -> Path:
    return DATA_DIR / f".last-run-{platform_mc}"


def _check_cooldown(platform_mc: str) -> None:
    """Reject a new crawl on the same platform inside the cooldown window."""
    marker = _cooldown_file(platform_mc)
    if not marker.is_file():
        return
    try:
        last = float(marker.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return
    elapsed = time.time() - last
    if elapsed < COOLDOWN_SECONDS:
        raise McError(
            f"同平台（{platform_mc}）两次抓取需间隔 {COOLDOWN_SECONDS // 60} 分钟"
            f"（上次结束于 {int(elapsed // 60)} 分钟前）——保护你的登录账号不触发风控。"
            "多个关键词合并进一次 --keywords、多条链接合并进一次 --ids；"
            "确有必要立即重抓时加 --force。"
        )


def _mark_cooldown(platform_mc: str) -> None:
    """Stamp after a data-producing crawl so the next one waits its turn."""
    marker = _cooldown_file(platform_mc)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def crawl(
    mode: str,
    platform: str,
    keywords: str = "",
    ids: list[str] | None = None,
    max_notes: int = 20,
    comments: bool = True,
    login: str = "qrcode",
    cookies: str = "",
    headless: bool = False,
    timeout: int = 900,
    out_dir: Path | str | None = None,
    force: bool = False,
    log: Callable[[str], None] = _log,
) -> dict:
    """End-to-end: validate install → cooldown check → run crawler → parse output."""
    platform_mc = normalize_platform(platform)
    if not force:
        _check_cooldown(platform_mc)
    run = run_crawl(
        build_crawler_args(mode, platform_mc, keywords, ids, max_notes,
                           comments=comments, login=login, cookies=cookies,
                           headless=headless, out_dir=out_dir),
        timeout=timeout, log=log,
    )
    result = parse_results(mode, platform_mc, out_dir)
    if result["ok"] and result["count"] > 0:
        _mark_cooldown(platform_mc)
    result["run"] = {
        "returncode": run["returncode"],
        "timed_out": run["timed_out"],
        "elapsed_seconds": run["elapsed_seconds"],
    }
    if not result["ok"] and run["timed_out"]:
        result["error"] = "timeout_no_output"
        result["hint"] = (
            "爬取超时且无输出。最常见原因：浏览器弹出后没有完成扫码登录。"
            "重新运行一次，在浏览器窗口里完成登录；登录态保存后不再需要扫码。"
        )
    return result
