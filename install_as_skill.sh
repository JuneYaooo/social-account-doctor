#!/bin/bash

##############################################################################
# social-account-doctor -- Skill 安装脚本
#
# 把当前仓库内容拷贝到指定 agent 的 skills 目录，默认保持 Claude 兼容。
# 并安装 Python 依赖 + tikhub CLI 软链 + 引导配置 .env。
#
# 用法：bash install_as_skill.sh [--target claude|codex|cursor|openclaw] [--skip-deps]
#       bash install_as_skill.sh --skill-dir /absolute/path [--skip-deps]
#
# pip 源会在官方 / 清华 / 阿里里探测选最快（国内裸连 pypi.org 常常只有几十 KB/s，
# 镜像能快一到两个数量级）；设 PIP_INDEX_URL 环境变量可强制指定，不探测。
##############################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info()    { echo -e "${BLUE}(i)  $1${NC}"; }
print_success() { echo -e "${GREEN}[OK] $1${NC}"; }
print_warning() { echo -e "${YELLOW}(!)  $1${NC}"; }
print_error()   { echo -e "${RED}[X] $1${NC}"; }
print_header()  { echo ""; echo "========================================"; echo "$1"; echo "========================================"; echo ""; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# 选最快的 pip 源：官方 / 清华 / 阿里逐个 HEAD 探测（各 4s 上限）。
# 结果写进 PIP_INDEX_ARGS；用户已设 PIP_INDEX_URL / PIP_INDEX 时不干预。
PIP_INDEX_ARGS=""
pick_pip_index() {
    if [ -n "${PIP_INDEX_URL:-}" ] || [ -n "${PIP_INDEX:-}" ]; then
        print_info "pip 源：使用环境变量 PIP_INDEX_URL/PIP_INDEX（不覆盖）"
        return
    fi
    command_exists curl || { print_info "pip 源：无 curl 不探测，用默认源"; return; }
    local best_url="" best_t="" url t
    for url in "https://pypi.org/simple/" "https://pypi.tuna.tsinghua.edu.cn/simple/" "https://mirrors.aliyun.com/pypi/simple/"; do
        t="$(curl -o /dev/null -sk -m 4 -w '%{time_total}' "$url" 2>/dev/null)" || continue
        [ -n "$t" ] || continue
        if [ -z "$best_t" ] || awk -v a="$t" -v b="$best_t" 'BEGIN{exit !(a<b)}'; then
            best_t="$t"
            best_url="$url"
        fi
    done
    if [ -z "$best_url" ]; then
        print_warning "pip 源探测全部失败，使用 pip 默认源"
        return
    fi
    case "$best_url" in
        https://pypi.org/*) print_info "pip 源：官方 PyPI（探测最快，${best_t}s）" ;;
        *) PIP_INDEX_ARGS="-i $best_url"
           print_info "pip 源：$best_url（探测最快，${best_t}s；设 PIP_INDEX_URL 可覆盖）" ;;
    esac
}

# 装 Python 依赖的三级回退（重试自动 --no-cache-dir：首次失败后缓存即嫌疑对象，
# pip 缓存跨版本共享，换 pip 版本治不了缓存损坏）：
#   直装（venv/conda/CLT Python 直接成功）→ --user → --user --break-system-packages
# 第三级是 PEP 668（externally-managed-environment，新 Debian/Ubuntu/Homebrew Python）
# 的标准解法，只写用户目录 ~/.local（mac 上是 ~/Library/Python），不动系统包。
pip_install_reqs() {
    local pip_bin
    if command_exists pip3; then pip_bin="pip3"; else pip_bin="pip"; fi
    local req="$1"
    local common="--timeout 60 --disable-pip-version-check"
    # shellcheck disable=SC2086
    if $pip_bin install $common $PIP_INDEX_ARGS -r "$req"; then return 0; fi
    print_warning "直接安装失败，改用 --user --no-cache-dir 重试"
    # shellcheck disable=SC2086
    if $pip_bin install $common --no-cache-dir $PIP_INDEX_ARGS --user -r "$req"; then return 0; fi
    print_warning "--user 也被拒（多为 externally-managed-environment），尝试 --break-system-packages"
    # shellcheck disable=SC2086
    if $pip_bin install $common --no-cache-dir $PIP_INDEX_ARGS --user --break-system-packages -r "$req"; then return 0; fi
    return 1
}

ENV_BACKUP=""
cleanup() {
    if [ -n "$ENV_BACKUP" ] && [ -f "$ENV_BACKUP" ]; then
        rm -f "$ENV_BACKUP"
    fi
}

resolve_skill_dir() {
    TARGET="claude"
    CUSTOM_SKILL_DIR=""
    SKIP_DEPS=0
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --target)
                [ "$#" -ge 2 ] || { print_error "--target 需要参数"; exit 2; }
                TARGET="$2"
                shift 2
                ;;
            --skill-dir)
                [ "$#" -ge 2 ] || { print_error "--skill-dir 需要参数"; exit 2; }
                CUSTOM_SKILL_DIR="$2"
                shift 2
                ;;
            --skip-deps)
                SKIP_DEPS=1
                shift
                ;;
            -h|--help)
                echo "用法: bash install_as_skill.sh [--target claude|codex|cursor|openclaw] [--skill-dir PATH] [--skip-deps]"
                exit 0
                ;;
            *)
                print_error "未知参数: $1"
                exit 2
                ;;
        esac
    done

    if [ -n "$CUSTOM_SKILL_DIR" ]; then
        case "$CUSTOM_SKILL_DIR" in
            /*) SKILL_DIR="$CUSTOM_SKILL_DIR" ;;
            *) print_error "--skill-dir 必须是绝对路径"; exit 2 ;;
        esac
        return
    fi

    case "$TARGET" in
        claude)  SKILL_DIR="$HOME/.claude/skills/social-account-doctor" ;;
        codex)   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/social-account-doctor" ;;
        cursor)  SKILL_DIR="$HOME/.cursor/skills/social-account-doctor" ;;
        openclaw) SKILL_DIR="$HOME/.openclaw/skills/social-account-doctor" ;;
        *) print_error "不支持的 target: $TARGET"; exit 2 ;;
    esac
}

main() {
    print_header "social-account-doctor -- 安装"

    resolve_skill_dir "$@"
    print_info "目标目录: $SKILL_DIR"

    if [ -d "$SKILL_DIR" ]; then
        print_warning "Skill 目录已存在: $SKILL_DIR"
        read -p "是否覆盖？(y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "取消"
            exit 0
        fi
        if [ -f "$SKILL_DIR/.env" ]; then
            ENV_BACKUP="$(mktemp "${TMPDIR:-/tmp}/social-account-doctor.env.XXXXXX")"
            cp "$SKILL_DIR/.env" "$ENV_BACKUP"
            print_info "已临时备份现有 .env"
        fi
        rm -rf "$SKILL_DIR"
    fi

    print_info "创建 Skill 目录..."
    mkdir -p "$SKILL_DIR"
    print_success "目录已创建"

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    print_info "复制项目文件..."
    rsync -a \
        --exclude='.git' \
        --exclude='reports' \
        --exclude='assets' \
        --exclude='output' \
        --exclude='vendor' \
        --exclude='venv' \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='.pytest_cache' \
        --exclude='.env' \
        "$SCRIPT_DIR/" "$SKILL_DIR/"
    print_success "文件复制完成"

    if [ -n "$ENV_BACKUP" ] && [ -f "$ENV_BACKUP" ]; then
        mv "$ENV_BACKUP" "$SKILL_DIR/.env"
        ENV_BACKUP=""
        print_success "已恢复用户 .env"
    fi

    print_info "检查 Python 环境..."
    if ! command_exists python3; then
        print_error "未找到 python3，请先安装 Python 3.10+"
        exit 1
    fi
    print_success "Python: $(python3 --version)"

    if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
        print_error "需要 Python 3.10+，当前为 $(python3 --version 2>&1)"
        exit 1
    fi

    if [ "$SKIP_DEPS" -eq 1 ]; then
        print_warning "已按 --skip-deps 跳过 Python 依赖安装"
    else
        print_info "安装 Python 依赖（进度逐行输出，首次视网速几分钟）..."
        pick_pip_index
        if pip_install_reqs "$SKILL_DIR/requirements.txt"; then
            print_success "依赖安装完成"
        else
            print_warning "Python 依赖自动安装失败。skill 文件已就位，请稍后手动执行："
            print_info "  pip3 install -r $SKILL_DIR/requirements.txt"
            if [ -n "$PIP_INDEX_ARGS" ]; then
                print_info "  （国内加速：pip3 $PIP_INDEX_ARGS -r $SKILL_DIR/requirements.txt）"
            fi
        fi
    fi

    print_header "配置 tikhub CLI"

    chmod +x "$SKILL_DIR/tikhub/bin/tikhub" 2>/dev/null || true
    mkdir -p "$HOME/.local/bin"
    ln -sf "$SKILL_DIR/tikhub/bin/tikhub" "$HOME/.local/bin/tikhub"
    print_success "已软链 tikhub -> ~/.local/bin/tikhub"

    chmod +x "$SKILL_DIR/mediacrawler/bin/mc" 2>/dev/null || true
    ln -sf "$SKILL_DIR/mediacrawler/bin/mc" "$HOME/.local/bin/mc"
    print_success "已软链 mc -> ~/.local/bin/mc（可选的登录式数据源，免 TikHub key）"

    if ! echo ":$PATH:" | grep -q ":$HOME/.local/bin:"; then
        print_warning "~/.local/bin 不在 PATH 中，请把下面一行加进 shell rc："
        print_info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi

    print_header "配置 API 密钥"

    if [ -f "$SKILL_DIR/.env" ]; then
        print_info "已存在 .env，跳过"
    else
        cp "$SKILL_DIR/.env.example" "$SKILL_DIR/.env"
        print_success "已生成 $SKILL_DIR/.env"
        print_warning "请编辑该文件填入 VIDEO_ANALYSIS_* / AUDIO_TRANSCRIPTION_* 等密钥"
    fi

    if ! grep -q "^TIKHUB_API_KEY=" "$SKILL_DIR/.env" 2>/dev/null || \
       grep -q "^TIKHUB_API_KEY=your-tikhub-key$" "$SKILL_DIR/.env" 2>/dev/null; then
        print_info "未配置 TIKHUB_API_KEY（可选：付费的 TikHub API，需要稳定结构化数据或视频号时用，申请: https://tikhub.io/ ）"
        print_info "  平台数据源优先级：agent 自带 computer use / 浏览器（首选，零配置）> opencli > TikHub > mc（最后手段）"
        print_info "  mc 是最后手段（上游反爬加剧）: mc --setup # 仅当其他数据源都不可用时"
    fi

    print_header "安装完成"

    print_success "已装到 $SKILL_DIR"
    echo ""
    print_info "下一步："
    print_info "  1. 编辑 .env 填多模态 API key:  nano $SKILL_DIR/.env"
    print_info "  2. 平台数据源按优先级（越高越像真人、越安全）："
    print_info "     a. agent 自带 computer use / 浏览器工具（首选，零配置，直接访问平台页面）"
    print_info "     b. opencli"
    print_info "     c. TikHub（付费，稳定，五平台含视频号）:.env 填 TIKHUB_API_KEY"
    print_info "     d. mc --setup（最后手段：上游反爬加剧，账号风控风险最高）"
    print_info "  3. 重启当前 agent 宿主让 skill 生效"
    print_info '  4. 直接对当前 agent 说："找对标 / 拆这条爆款 / 对着这条仿写"'
    echo ""
    print_info "冒烟测试（可选）："
    print_info "  tikhub --health"
    print_info "  tikhub list xiaohongshu search"
    print_info "  mc --status      # 登录式数据源（需先 mc --setup）"
    echo ""
}

trap cleanup EXIT
trap 'print_error "安装过程出错"; exit 1' ERR

main "$@"
