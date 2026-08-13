#!/bin/bash

##############################################################################
# social-account-doctor -- Skill 安装脚本
#
# 把当前仓库内容拷贝到指定 agent 的 skills 目录，默认保持 Claude 兼容。
# 并安装 Python 依赖 + tikhub CLI 软链 + 引导配置 .env。
#
# 用法：bash install_as_skill.sh [--target claude|codex|cursor|openclaw] [--skip-deps]
#       bash install_as_skill.sh --skill-dir /absolute/path [--skip-deps]
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
        --exclude='venv' \
        --exclude='.venv' \
        --exclude='__pycache__' \
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
        print_info "安装 Python 依赖..."
        if command_exists pip3; then
            pip3 install -q -r "$SKILL_DIR/requirements.txt"
        else
            pip install -q -r "$SKILL_DIR/requirements.txt"
        fi
        print_success "依赖安装完成"
    fi

    print_header "配置 tikhub CLI"

    chmod +x "$SKILL_DIR/tikhub/bin/tikhub" 2>/dev/null || true
    mkdir -p "$HOME/.local/bin"
    ln -sf "$SKILL_DIR/tikhub/bin/tikhub" "$HOME/.local/bin/tikhub"
    print_success "已软链 tikhub -> ~/.local/bin/tikhub"

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
        print_warning "请在 $SKILL_DIR/.env 填入有效的 TIKHUB_API_KEY"
        print_info "  申请 key: https://tikhub.io/"
    fi

    print_header "安装完成"

    print_success "已装到 $SKILL_DIR"
    echo ""
    print_info "下一步："
    print_info "  1. 编辑 .env 填多模态 API key:  nano $SKILL_DIR/.env"
    print_info "  2. 在同一 .env 填入 TIKHUB_API_KEY"
    print_info "  3. 重启当前 agent 宿主让 skill 生效"
    print_info '  4. 直接对当前 agent 说："找对标 / 拆这条爆款 / 对着这条仿写"'
    echo ""
    print_info "冒烟测试（可选）："
    print_info "  tikhub --health"
    print_info "  tikhub list xiaohongshu search"
    echo ""
}

trap cleanup EXIT
trap 'print_error "安装过程出错"; exit 1' ERR

main "$@"
