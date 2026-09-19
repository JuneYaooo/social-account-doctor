"""MediaCrawler adapter — 用自己的账号登录抓平台数据，不需要 TikHub key.

把 NanmiCoder/MediaCrawler（Playwright 真实浏览器爬虫）包装成与本仓库
``tikhub`` CLI 同风格的本地数据源：

    mc search  --platform xiaohongshu --keywords "词1,词2"   # 关键词搜（find）
    mc detail  --platform douyin --ids "url1,url2"           # 作品详情（crack）
    mc creator --platform xhs --ids "profile_url"            # 创作者主页（账号诊断）

首次使用 ``mc --setup``：克隆 MediaCrawler 到 vendor/、建独立 venv、装
Playwright chromium，并把 ENABLE_CDP_MODE 补丁为 False（走标准 Playwright
模式，登录态落在 vendor/MediaCrawler/browser_data/，扫码一次长期复用）。

setup 的下载源会自动择优：pip 在官方 PyPI / 清华 / 阿里镜像里探测选最快，
Chromium 走 npmmirror 镜像（仅当明显更快），GitHub 克隆失败时回退 gh 代理。
用户已设 PIP_INDEX_URL / PLAYWRIGHT_DOWNLOAD_HOST / MC_GIT_URL 时一律尊重
不覆盖；``MC_NO_MIRROR=1``（或 CLI ``--no-mirror``）可整体禁用。依赖先装
requirements-lean.txt（mc 路径够用的裁剪版），smoke test 失败自动回退上游
全量 requirements.txt。

所有机器可读结果以 JSON 打到 stdout；人类可读进度走 stderr。
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
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

# 同平台两次抓取的最小间隔（秒）。用户账号登录抓取，抓太密会触发平台风控；
# 30 分钟对应「同账号同平台每天 ≤ 4-6 次」的安全预算，可用 MC_COOLDOWN_SECONDS
# 覆盖。合并关键词（--keywords "词1,词2"）和批量 ID（--ids "url1,url2"）一次
# 跑完，不要拆成多次调用绕冷却。用户明确要求时可用 --force 覆盖。
COOLDOWN_SECONDS = int(os.environ.get("MC_COOLDOWN_SECONDS", "1800"))
# 抓取失败的退避间隔（秒）。失败往往发生在风控敏感期（验证码 / 登录失效 /
# 被限流），立即重试只会继续加压，所以失败也写冷却标记，只是短一截。
FAILURE_COOLDOWN_SECONDS = int(os.environ.get("MC_FAILURE_COOLDOWN_SECONDS", "600"))
# 抓取锁超过此时长（秒）视为崩溃残留，可被新进程抢占
CRAWL_LOCK_STALE_SECONDS = 7200
# 单次 run 体量硬上限（超了直接拒绝，拆多次跑会被冷却拦住）。风控看的是
# 长期总量，不是单次频率；要更多数据就分天抓或改走 TikHub。
MAX_KEYWORDS_PER_RUN = int(os.environ.get("MC_MAX_KEYWORDS", "3"))
MAX_DETAIL_IDS_PER_RUN = int(os.environ.get("MC_MAX_DETAIL_IDS", "5"))
MAX_CREATOR_IDS_PER_RUN = int(os.environ.get("MC_MAX_CREATOR_IDS", "2"))

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


# ---------------------------------------------------------------------------
# setup 网络加速：下载源自动择优（国内裸连 GitHub/PyPI/Playwright CDN 常常只有几十 KB/s，
# 镜像源能快一到两个数量级）。所有选择都可以被用户环境变量覆盖。
# ---------------------------------------------------------------------------

PIP_INDEX_CANDIDATES: list[tuple[str, str]] = [
    ("官方 PyPI", "https://pypi.org/simple"),
    ("清华 PyPI 镜像", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里 PyPI 镜像", "https://mirrors.aliyun.com/pypi/simple"),
]
PLAYWRIGHT_OFFICIAL_HOST = "https://cdn.playwright.dev"
PLAYWRIGHT_MIRROR_HOST = "https://registry.npmmirror.com/-/binary/playwright"
GIT_MIRROR_PREFIXES = [
    "https://gh-proxy.com/",
    "https://ghfast.top/",
]
LEAN_REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements-lean.txt"


def _no_mirror() -> bool:
    return os.environ.get("MC_NO_MIRROR") == "1"


def _probe_ms(url: str, timeout: float = 4.0) -> float | None:
    """HEAD 探测往返毫秒数；连不上返回 None。

    任何 HTTP 状态码（含 4xx）都算可达——比的是到源站链路的快慢，
    不是业务路径是否存在（cdn.playwright.dev 根路径就返回 400）。
    """
    started = time.time()
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "social-account-doctor"})
        urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError:
        pass
    except Exception:
        return None
    return round((time.time() - started) * 1000, 1)


def _pick_fastest(candidates: list[tuple[str, str]]) -> tuple[str, str, float | None]:
    """并发探测候选源，返回 (名字, URL, 最快耗时 ms)；全部不可达时耗时为 None。"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(candidates)) as pool:
        latencies = list(pool.map(lambda c: _probe_ms(c[1]), candidates))
    paired = [(ms if ms is not None else float("inf"), name, url)
              for (name, url), ms in zip(candidates, latencies)]
    ms, name, url = min(paired, key=lambda item: item[0])
    return name, url, (None if ms == float("inf") else ms)


def pip_index_args(log: Callable[[str], None] = _log) -> tuple[list[str], str]:
    """pip install 的额外参数；返回 (args, 源标签)。已设 PIP_INDEX_URL/PIP_INDEX 时尊重 pip 原生行为。"""
    if os.environ.get("PIP_INDEX_URL") or os.environ.get("PIP_INDEX"):
        log("[mc] 检测到 PIP_INDEX_URL/PIP_INDEX，pip 源以环境变量为准")
        return [], "env"
    if _no_mirror():
        return [], "direct"
    name, url, ms = _pick_fastest(PIP_INDEX_CANDIDATES)
    if ms is None:
        log("[mc] 所有 pip 源探测失败，回退 pip 默认源")
        return [], "default"
    log(f"[mc] pip 源: {name}（探测 {ms:.0f}ms，自动择优）")
    if url == PIP_INDEX_CANDIDATES[0][1]:
        return [], name
    return ["-i", url], name


def playwright_mirror_env(log: Callable[[str], None] = _log) -> dict[str, str]:
    """需要注入 PLAYWRIGHT_DOWNLOAD_HOST 时返回它，否则空 dict（走官方 CDN）。"""
    if os.environ.get("PLAYWRIGHT_DOWNLOAD_HOST"):
        log("[mc] 检测到 PLAYWRIGHT_DOWNLOAD_HOST，Chromium 下载源以环境变量为准")
        return {}
    if _no_mirror():
        return {}
    official = _probe_ms(PLAYWRIGHT_OFFICIAL_HOST)
    mirror = _probe_ms(PLAYWRIGHT_MIRROR_HOST)
    if mirror is not None and (official is None or mirror * 2 < official):
        log(f"[mc] Chromium 下载走 npmmirror 镜像（{mirror:.0f}ms vs 官方 "
            f"{'不可达' if official is None else f'{official:.0f}ms'}）")
        return {"PLAYWRIGHT_DOWNLOAD_HOST": PLAYWRIGHT_MIRROR_HOST}
    return {}


def clone_url_candidates(log: Callable[[str], None] = _log) -> list[tuple[str, str]]:
    """按尝试顺序返回 (URL, 标签)。MC_GIT_URL 一票优先；github 可达时直连优先、镜像垫后。"""
    env_url = os.environ.get("MC_GIT_URL")
    if env_url:
        log(f"[mc] 使用 MC_GIT_URL={env_url}")
        return [(env_url, "MC_GIT_URL")]
    direct = (MC_GIT_URL, "github 直连")
    if _no_mirror():
        return [direct]
    mirrors = [(prefix + MC_GIT_URL, f"gh 代理 {prefix}") for prefix in GIT_MIRROR_PREFIXES]
    if _probe_ms("https://github.com", timeout=5.0) is None:
        log("[mc] github.com 探测不可达，优先尝试 gh 代理镜像")
        return mirrors + [direct]
    return [direct] + mirrors


def _run_stream(
    cmd: list[str],
    log: Callable[[str], None] = _log,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    tail_lines: int = 25,
) -> tuple[int, list[str]]:
    """跑长下载命令（pip / playwright install）：输出逐行转发到 stderr 日志，
    保持 stdout 纯 JSON 契约；返回 (returncode, 尾部输出) 供错误报告。超时杀进程组。"""
    started = time.time()
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        env=env, cwd=cwd, start_new_session=True,
    )
    tail: deque[str] = deque(maxlen=tail_lines)
    done = threading.Event()

    def _pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                tail.append(line)
                log(f"    {line}")
        done.set()

    threading.Thread(target=_pump, daemon=True).start()
    deadline = started + timeout
    while not done.wait(timeout=1.0) and time.time() < deadline:
        pass
    if not done.is_set():
        log(f"[mc] 超过 {timeout}s，终止下载进程")
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, AttributeError):  # AttributeError: os.killpg Windows 不存在
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, AttributeError):  # AttributeError: os.killpg Windows 不存在
                pass
            proc.wait(timeout=30)
        done.wait(timeout=5)
    else:
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
    log(f"[mc] 完成（{time.time() - started:.0f}s，exit {proc.returncode}）")
    return proc.returncode, list(tail)


def _smoke_test(vpy: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(vpy), "main.py", "--help"], cwd=MC_DIR, capture_output=True, text=True, timeout=120,
    )


def _parse_requirements(req_file: Path) -> list[str]:
    """把 requirements 文件拆成逐包 spec 列表（跳过注释和空行）。"""
    specs = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        spec = line.split("#", 1)[0].strip()
        if spec and not spec.startswith("-"):
            specs.append(spec)
    return specs


def _pip_install_specs(
    vpy: Path, specs: list[str], index_args: list[str],
    log: Callable[[str], None] = _log, extra_flags: tuple[str, ...] = (),
) -> bool:
    cmd = [str(vpy), "-m", "pip", "install", "--timeout", "60", "--disable-pip-version-check",
           *extra_flags, *index_args, *specs]
    rc, _tail = _run_stream(cmd, log=log, timeout=1800)
    return rc == 0


def _pip_install_one(vpy: Path, spec: str, index_args: list[str],
                     log: Callable[[str], None] = _log) -> bool:
    """单包三级重试。

    ① 默认安装失败 → ② ``--no-cache-dir``：pip 的 HTTP 缓存（~/.cache/pip）里
    可能存着损坏的 tarball——它跨 pip 版本和 TMPDIR 共享，换版本/换临时目录都
    治不了，只有绕开缓存重新下载（真实案例：用户端 jieba/pyexecjs 反复
    「临时目录冲突」，手动下载解压能装，就是缓存损坏的特征）→
    ③ ``--no-build-isolation``：jieba 0.42.1 / pyexecjs 1.5.1 这类没有 wheel
    的老源码包，用 venv 自带 setuptools 直接装，绕开隔离构建的临时目录流程。
    """
    for attempt, flags in enumerate((
        (),
        ("--no-cache-dir",),
        ("--no-cache-dir", "--no-build-isolation"),
    ), start=1):
        reason = {1: "默认", 2: "清缓存", 3: "关构建隔离"}[attempt]
        log(f"[mc] 装包 {spec}（第 {attempt}/3 次，{reason}）")
        if "--no-build-isolation" in flags:
            # Python 3.12 的 venv 不再自带 setuptools，关隔离构建前先补齐
            _pip_install_specs(vpy, ["setuptools", "wheel"], index_args, log)
        if _pip_install_specs(vpy, [spec], index_args, log, extra_flags=flags):
            return True
    return False


def _pip_install(vpy: Path, req_file: Path, index_args: list[str],
                 log: Callable[[str], None] = _log) -> None:
    if _pip_install_specs(vpy, ["-r", str(req_file)], index_args, log):
        return
    # 整体装失败 → 逐包装 + 单包三级重试，把「一个包坏拖死全部依赖」变成
    # 「坏包自动恢复或被精确点名」，不再需要 agent 手动逐个救
    specs = _parse_requirements(req_file)
    log(f"[mc] 整体安装失败，改为逐包安装（{len(specs)} 个包，每包默认→清缓存→关构建隔离三级重试）")
    failed = [spec for spec in specs if not _pip_install_one(vpy, spec, index_args, log)]
    if failed:
        raise McError(
            f"依赖安装失败（{req_file.name}）: {', '.join(failed)}。"
            f"手动修复：{vpy} -m pip install --no-cache-dir --no-build-isolation {' '.join(failed)}"
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


# 上游固定 2s 间隔是典型机器特征；快手 core 自带抖动，其余平台靠这个补丁
PACING_CORE_FILES = (
    "media_platform/xhs/core.py",
    "media_platform/douyin/core.py",
    "media_platform/kuaishou/core.py",
    "media_platform/bilibili/core.py",
)
_JITTER = "config.CRAWLER_MAX_SLEEP_SEC + random.uniform(0, config.CRAWLER_MAX_SLEEP_SEC)"


def _patch_jitter(text: str) -> str:
    # 确保有 import random（bilibili core 没有）；幂等
    if not re.search(r"^import random$", text, re.M):
        text = text.replace("import asyncio\n", "import asyncio\nimport random\n", 1)
    # 两种节奏形态都打上抖动：直接 sleep 和先赋值再 sleep
    text = text.replace(f"asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)",
                        f"asyncio.sleep({_JITTER})")
    text = text.replace("crawl_interval = config.CRAWLER_MAX_SLEEP_SEC",
                        f"crawl_interval = {_JITTER}")
    return text


def patch_pacing(mc_dir: Path | None = None) -> dict[str, bool]:
    """请求间隔随机化 + 基础间隔 2s→3s（抖动后 3-6s 随机停顿）。

    固定间隔是平台异常检测最经典的机器特征。幂等、非致命：某个文件找不到
    匹配模式就保持原样（跑起来仍是安全的固定间隔，只是少了随机性）。
    """
    mc_dir = mc_dir or MC_DIR
    result: dict[str, bool] = {}
    cfg = mc_dir / "config" / "base_config.py"
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8")
        patched = text.replace("CRAWLER_MAX_SLEEP_SEC = 2", "CRAWLER_MAX_SLEEP_SEC = 3")
        if patched != text:
            cfg.write_text(patched, encoding="utf-8")
        result["base_sleep_3s"] = "CRAWLER_MAX_SLEEP_SEC = 3" in cfg.read_text(encoding="utf-8")
    for rel in PACING_CORE_FILES:
        path = mc_dir / rel
        if not path.is_file():
            continue
        patched = _patch_jitter(path.read_text(encoding="utf-8"))
        if patched != path.read_text(encoding="utf-8"):
            path.write_text(patched, encoding="utf-8")
        result[rel.split("/")[1]] = _JITTER in path.read_text(encoding="utf-8")
    return result


def pacing_patched(mc_dir: Path | None = None) -> bool:
    """抖动补丁是否已应用（任一平台 core 带抖动即视为已打）。"""
    mc_dir = mc_dir or MC_DIR
    return any(
        _JITTER in (mc_dir / rel).read_text(encoding="utf-8")
        for rel in PACING_CORE_FILES if (mc_dir / rel).is_file()
    )


# ---------------------------------------------------------------------------
# 词云可选化：jieba 0.42.1（2020 年后无更新、无 wheel）和 wordcloud（带 C 扩展）
# 是用户环境里源码构建故障的重灾区，但只被词云功能用到，而 mc 从不启用词云
# （ENABLE_GET_WORDCLOUD 默认 False）。补丁后这三个包从必装变成可选，
# 安装关键路径上只剩有 wheel 的包。
# ---------------------------------------------------------------------------

_WORDS_PY = "tools/words.py"


def _patch_optional_wordcloud_text(text: str) -> str:
    if "WORDCLOUD_DEPS_READY" in text:
        return text  # 已打过
    old_imports = (
        "import aiofiles\n"
        "import jieba\n"
        "import matplotlib.pyplot as plt\n"
        "from wordcloud import WordCloud\n"
    )
    if old_imports not in text:
        return text  # 上游结构变了，保持原样（词云三件套退回必装）
    patched = text.replace(
        old_imports,
        "import aiofiles\n"
        "try:\n"
        "    import jieba\n"
        "    import matplotlib.pyplot as plt\n"
        "    from wordcloud import WordCloud\n"
        "    WORDCLOUD_DEPS_READY = True\n"
        "except ImportError:  # 词云是可选功能（ENABLE_GET_WORDCLOUD 默认 False）\n"
        "    WORDCLOUD_DEPS_READY = False\n",
        1,
    )
    old_init = "    def __init__(self):\n        logging.getLogger('jieba').setLevel(logging.WARNING)"
    new_init = (
        "    def __init__(self):\n"
        "        if not WORDCLOUD_DEPS_READY:\n"
        "            raise RuntimeError('词云功能需要可选依赖 jieba/matplotlib/wordcloud；"
        "安装后再开启 ENABLE_GET_WORDCLOUD')\n"
        "        logging.getLogger('jieba').setLevel(logging.WARNING)"
    )
    if old_init in patched:
        patched = patched.replace(old_init, new_init, 1)
    return patched


def patch_optional_wordcloud(mc_dir: Path | None = None) -> bool:
    """幂等、非致命：上游结构不匹配时返回 False，词云三件套退回必装路径。"""
    mc_dir = mc_dir or MC_DIR
    path = mc_dir / _WORDS_PY
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    patched = _patch_optional_wordcloud_text(text)
    if patched == text:
        return False
    path.write_text(patched, encoding="utf-8")
    return True


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
        info["pacing_patched"] = pacing_patched()
        words_py = MC_DIR / _WORDS_PY
        if words_py.is_file():
            info["wordcloud_optional"] = "WORDCLOUD_DEPS_READY" in words_py.read_text(encoding="utf-8")
        info["ok"] = info["config_patched"]
    info["version"] = _read_version_file()
    return info


def setup(force: bool = False, log: Callable[[str], None] = _log) -> dict:
    """Clone MediaCrawler, build venv, install deps + Playwright chromium（下载源自动择优）."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    steps: dict[str, Any] = {}

    py = find_python()
    if py is None:
        raise McError(
            "需要 Python >= 3.10 来创建 MediaCrawler 虚拟环境；"
            "用 MC_PYTHON 环境变量指定解释器后重试"
        )
    steps["python"] = str(py)

    # 1. clone（MC_GIT_URL > 直连（重试 2 次）> gh 代理镜像，全部失败才报错）
    if (MC_DIR / "main.py").is_file() and not force:
        steps["clone"] = "skipped (already cloned)"
    else:
        if MC_DIR.exists():
            log(f"[mc] 移除已有目录 {MC_DIR}")
            shutil.rmtree(MC_DIR)
        last_err = ""
        cloned_from = ""
        cloned = False
        for url, label in clone_url_candidates(log):
            tries = 2 if url == MC_GIT_URL else 1
            for attempt in range(1, tries + 1):
                log(f"[mc] 克隆 MediaCrawler ← {label}（第 {attempt}/{tries} 次）")
                result = _git(["clone", "--depth", "1", url, str(MC_DIR)])
                if result.returncode == 0:
                    cloned, cloned_from = True, label
                    break
                last_err = result.stderr.strip()[:300]
                if MC_DIR.exists():
                    shutil.rmtree(MC_DIR, ignore_errors=True)
                time.sleep(2 * attempt)
            if cloned:
                break
        if not cloned:
            raise McError(
                f"git clone 失败: {last_err}。可任选其一：设 MC_GIT_URL 指向可达的克隆地址；"
                "手动克隆后放到 vendor/MediaCrawler 再重跑 mc --setup；或配置 HTTPS_PROXY 后重试"
            )
        steps["clone"] = f"ok via {cloned_from}"
        # pin 到适配时的 commit；HEAD 已是目标或上游漂移导致 fetch 失败则保留原样
        actual_sha = _git(["rev-parse", "HEAD"], cwd=MC_DIR).stdout.strip()
        if actual_sha != PINNED_COMMIT:
            pin = _git(["fetch", "--depth", "1", "origin", PINNED_COMMIT], cwd=MC_DIR)
            if pin.returncode == 0 and _git(["checkout", "--quiet", PINNED_COMMIT], cwd=MC_DIR).returncode == 0:
                steps["clone"] += f", pinned {PINNED_COMMIT[:12]}"
            else:
                steps["clone"] += ", default branch (pin failed, upstream may have moved)"
        else:
            steps["clone"] += f", pinned {PINNED_COMMIT[:12]}"

    actual_sha = _git(["rev-parse", "HEAD"], cwd=MC_DIR).stdout.strip()

    # 2. vendor 补丁（在装依赖前打，smoke test 跑的才是补丁后的代码）：
    #    CDP 关闭 / 节奏抖动 / 词云三件套可选化
    steps["config_patch"] = "applied" if patch_config() else "already patched"
    steps["pacing_patch"] = patch_pacing()
    steps["wordcloud_patch"] = "applied" if patch_optional_wordcloud() else "not needed"

    # 3. venv
    if venv_python().is_file() and not force:
        steps["venv"] = "skipped (already exists)"
    else:
        log(f"[mc] 创建虚拟环境 → {VENV_DIR}")
        result = subprocess.run([str(py), "-m", "venv", str(VENV_DIR)], capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise McError(f"venv 创建失败: {result.stderr.strip()[:300]}")
        steps["venv"] = "created"

    # 4. deps：精简 requirements 优先（mc 的 search/detail/creator + json 落盘路径够用），
    #    smoke test 不过就回退上游全量安装，保证行为不比原来差
    vpy = venv_python()
    index_args, index_name = pip_index_args(log)
    if LEAN_REQUIREMENTS.is_file():
        log(f"[mc] 安装精简依赖（{LEAN_REQUIREMENTS.name}，输出逐行转发在下方）")
        try:
            _pip_install(vpy, LEAN_REQUIREMENTS, index_args, log)
            smoke = _smoke_test(vpy)
            if smoke.returncode != 0:
                raise McError(f"精简依赖自检失败: {smoke.stderr.strip()[:200]}")
            steps["pip"] = f"lean via {index_name}"
        except McError as exc:
            log(f"[mc] {exc}；回退上游全量 requirements.txt")
            _pip_install(vpy, MC_DIR / "requirements.txt", index_args, log)
            steps["pip"] = f"full via {index_name} (lean fallback)"
    else:
        log("[mc] 安装 MediaCrawler 依赖（输出逐行转发在下方）")
        _pip_install(vpy, MC_DIR / "requirements.txt", index_args, log)
        steps["pip"] = f"full via {index_name}"

    # 5. playwright chromium（约 200MB，走择优后的下载源）
    log("[mc] 安装 Playwright chromium（约 200MB，取决于网速需要几分钟）")
    pw_env = os.environ.copy()
    pw_env.update(playwright_mirror_env(log))
    rc, tail = _run_stream(
        [str(vpy), "-m", "playwright", "install", "chromium"],
        log=log, timeout=1800, env=pw_env,
    )
    if rc != 0:
        raise McError(f"playwright install 失败: {' | '.join(tail[-3:])}")
    steps["playwright"] = "chromium installed"

    # 6. 版本记录 + smoke test
    VERSION_FILE.write_text(json.dumps({
        "pinned_commit": PINNED_COMMIT,
        "actual_commit": actual_sha,
        "setup_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # smoke test
    result = _smoke_test(vpy)
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
    max_comments_per_note: int = 10,
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


def _redact_cmd(cmd: list[str]) -> str:
    """日志用的命令行还原，cookie 值打码（进程列表里 --cookies 依然可见，
    共享机器慎用 cookie 登录，见 README）。"""
    parts: list[str] = []
    skip_value = False
    for item in cmd:
        if skip_value:
            parts.append("***")
            skip_value = False
        elif item == "--cookies":
            parts.append(item)
            skip_value = True
        elif item.startswith("--cookies="):
            parts.append("--cookies=***")
        else:
            parts.append(item)
    return " ".join(parts)


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
    _debug(f"run: {_redact_cmd(cmd)}")
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
        except (ProcessLookupError, PermissionError, AttributeError):  # AttributeError: os.killpg Windows 不存在
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, AttributeError):  # AttributeError: os.killpg Windows 不存在
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


def parse_results(mode: str, platform_mc: str, out_dir: Path | str | None = None,
                  since: float | None = None) -> dict:
    """Read MediaCrawler JSON output and normalize it for the analysis pipeline.

    ``since``（epoch 秒）只接受该时刻之后写入的结果文件——crawl 用它防止
    「本次抓取失败没写出新文件、却把历史文件当本次结果返回」的静默错误；
    单独复用历史数据（SKILL.md 的「先复用再抓」路径）不传 since，行为不变。
    """
    if mode not in CRAWL_MODES:
        raise McError(f"未知模式 {mode!r}")
    base = (Path(out_dir) if out_dir else DATA_DIR) / platform_mc / "json"
    content_files = _latest_files(base, f"{mode}_contents_*.json")
    if since is not None and content_files:
        fresh = [p for p in content_files if p.stat().st_mtime >= since]
        if not fresh:
            return {
                "ok": False,
                "error": "stale_data",
                "platform": platform_mc,
                "mode": mode,
                "items": [],
                "count": 0,
                "stale_files": [
                    {"path": str(p), "age_minutes": int((time.time() - p.stat().st_mtime) // 60)}
                    for p in content_files
                ],
                "hint": "本次抓取没有产出新数据（常见：未扫码登录 / 触发风控 / 超时中断）。"
                        "stale_files 是历史数据，除非明确要复用，不要当本次结果使用；"
                        "先 mc --status 检查登录态再重试。",
            }
        content_files = fresh
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


def _cooldown_expiry(platform_mc: str) -> float | None:
    """读冷却标记里存的「到期时间戳」（epoch 秒）；无标记 / 损坏返回 None。"""
    marker = _cooldown_file(platform_mc)
    if not marker.is_file():
        return None
    try:
        return float(marker.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _check_cooldown(platform_mc: str) -> None:
    """Reject a new crawl on the same platform inside the cooldown window."""
    expiry = _cooldown_expiry(platform_mc)
    if expiry is None:
        return
    remaining = expiry - time.time()
    if remaining > 0:
        raise McError(
            f"同平台（{platform_mc}）抓取冷却中，还需等 {int(remaining // 60) + 1} 分钟"
            "——保护登录账号不触发风控。注意：抓取失败也会进入退避，连续失败通常"
            "是登录失效或风控信号（先 mc --status 检查登录态），不要拿 --force 硬闯。"
            "多个关键词合并进一次 --keywords、多条链接合并进一次 --ids；"
            "确有必要立即重抓时加 --force。"
        )


def _mark_cooldown(platform_mc: str, seconds: int | None = None) -> None:
    """Stamp the cooldown expiry; 成功抓取用完整间隔，失败退避用短间隔。"""
    duration = COOLDOWN_SECONDS if seconds is None else seconds
    marker = _cooldown_file(platform_mc)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time() + duration), encoding="utf-8")
    except OSError:
        pass


def _lock_file() -> Path:
    """全局单实例锁：同一时间全机只允许一个抓取进程。跨平台并行同样拒绝——
    虽然各平台风控相互独立，但单实例最简单也最稳：不会出现两个 chromium、
    agent 也不会同时盯多个扫码窗口。"""
    return DATA_DIR / "crawl.lock"


def _acquire_crawl_lock() -> Path | None:
    """O_CREAT|O_EXCL 原子创建；崩溃残留超时的锁可抢占。
    返回锁文件路径（调用方负责 finally 释放），拿不到返回 None。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = _lock_file()
    for _attempt in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
            except OSError:
                return None
            if age <= CRAWL_LOCK_STALE_SECONDS or _attempt:
                return None
            try:  # 崩溃残留的陈旧锁，清掉重试一次
                lock.unlink()
            except OSError:
                return None
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()} {time.time()}")
        return lock
    return None


def _check_volume_caps(mode: str, keywords: str, ids: list[str] | None) -> None:
    """单次 run 体量硬上限。超了直接拒绝并说明出路（分天 / 走 TikHub），
    而不是靠 agent 自觉遵守 SKILL.md 里的数字。"""
    if mode == "search":
        count = len([k for k in keywords.split(",") if k.strip()])
        if count > MAX_KEYWORDS_PER_RUN:
            raise McError(
                f"单次 search 最多 {MAX_KEYWORDS_PER_RUN} 个关键词（当前 {count}）——"
                "体量是风控的首要信号。要更多数据分天抓或改走 TikHub；"
                "确有特殊需要时设 MC_MAX_KEYWORDS 提高上限（自担风险）。"
            )
    elif mode == "detail":
        if len(ids or []) > MAX_DETAIL_IDS_PER_RUN:
            raise McError(
                f"单次 detail 最多 {MAX_DETAIL_IDS_PER_RUN} 条作品（当前 {len(ids)}）——"
                "先让用户从 find 结果里勾选真正要拆的 3-5 条；"
                "确有特殊需要时设 MC_MAX_DETAIL_IDS（自担风险）。"
            )
    elif mode == "creator":
        if len(ids or []) > MAX_CREATOR_IDS_PER_RUN:
            raise McError(
                f"单次 creator 最多 {MAX_CREATOR_IDS_PER_RUN} 个账号（当前 {len(ids)}）——"
                "账号诊断逐个跑，别一次拉一堆；"
                "确有特殊需要时设 MC_MAX_CREATOR_IDS（自担风险）。"
            )


def crawl(
    mode: str,
    platform: str,
    keywords: str = "",
    ids: list[str] | None = None,
    max_notes: int = 20,
    max_comments: int = 10,
    comments: bool | None = None,
    login: str = "qrcode",
    cookies: str = "",
    headless: bool = False,
    timeout: int = 900,
    out_dir: Path | str | None = None,
    force: bool = False,
    log: Callable[[str], None] = _log,
) -> dict:
    """End-to-end: lock → volume caps → cooldown check → run crawler → parse output."""
    platform_mc = normalize_platform(platform)
    # 评论默认按模式定：detail/creator（crack 拆解、账号诊断）真用评论内容；
    # search（find 找对标）只用互动计数——comment_count 笔记详情自带，逐条翻
    # 评论页会让单次 run 的请求数翻三倍，是最容易触发风控的行为。显式
    # --comments/--no-comments 永远优先。
    if comments is None:
        comments = mode != "search"
    # 体量硬上限（风控看长期总量；拆多次跑会被冷却拦住，别绕）
    _check_volume_caps(mode, keywords, ids)
    # 全局单实例锁（--force 也不绕过锁：锁保护的是浏览器 profile，不是频率）
    lock = _acquire_crawl_lock()
    if lock is None:
        raise McError(
            "已有另一个 mc 抓取进程在跑（全机单实例锁，跨平台也算并行）——并行会抢"
            "浏览器登录 profile、可能损坏登录态。等它跑完再试；确认是残留锁时删除 "
            f"{_lock_file()} 后重试。"
        )
    if not pacing_patched():
        log("[mc] 警告：请求节奏未打抖动补丁（固定间隔是典型机器特征），"
            "建议重跑 mc --setup 应用补丁")
    run_started = time.time()
    try:
        if not force:
            _check_cooldown(platform_mc)
        run = run_crawl(
            build_crawler_args(mode, platform_mc, keywords, ids, max_notes,
                               comments=comments, login=login, cookies=cookies,
                               headless=headless, out_dir=out_dir,
                               max_comments_per_note=max_comments),
            timeout=timeout, log=log,
        )
        # since=run_started：只认本次 run 写出的文件，防止失败时静默返回历史数据
        result = parse_results(mode, platform_mc, out_dir, since=run_started)
        if result["ok"] and result["count"] > 0:
            _mark_cooldown(platform_mc)
        else:
            # 失败退避：浏览器已拉起、请求已发出，即使没抓到数据也要冷却一截，
            # 防止 agent 在风控敏感期零间隔循环重试
            _mark_cooldown(platform_mc, seconds=FAILURE_COOLDOWN_SECONDS)
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
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
