#!/bin/bash

##############################################################################
# social-account-doctor -- Claude Code Skill 安装脚本
#
# 把当前仓库内容拷贝到 ~/.claude/skills/social-account-doctor/
# 并安装 Python 依赖 + tikhub CLI 软链 + 引导配置 .env。
#
# 用法：bash install_as_skill.sh
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

main() {
    print_header "social-account-doctor -- 安装"

    SKILL_DIR="$HOME/.claude/skills/social-account-doctor"
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
            cp "$SKILL_DIR/.env" "/tmp/social-account-doctor.env.bak"
            print_info "已备份现有 .env 到 /tmp/social-account-doctor.env.bak"
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

    if [ -f "/tmp/social-account-doctor.env.bak" ]; then
        mv "/tmp/social-account-doctor.env.bak" "$SKILL_DIR/.env"
        print_success "已恢复用户 .env"
    fi

    print_info "检查 Python 环境..."
    if ! command_exists python3; then
        print_error "未找到 python3，请先安装 Python 3.10+"
        exit 1
    fi
    print_success "Python: $(python3 --version)"

    print_info "安装 Python 依赖..."
    if command_exists pip3; then
        pip3 install -q -r "$SKILL_DIR/requirements.txt"
    else
        pip install -q -r "$SKILL_DIR/requirements.txt"
    fi
    print_success "依赖安装完成"

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

    if [ ! -f "$HOME/.claude/.env" ] || ! grep -q "TIKHUB_API_KEY" "$HOME/.claude/.env" 2>/dev/null; then
        print_warning "未检测到 TIKHUB_API_KEY，请执行："
        print_info "  echo 'TIKHUB_API_KEY=YOUR_KEY' >> ~/.claude/.env && chmod 600 ~/.claude/.env"
        print_info "  申请 key: https://tikhub.io/"
    fi

    print_header "安装完成"

    print_success "已装到 $SKILL_DIR"
    echo ""
    print_info "下一步："
    print_info "  1. 编辑 .env 填多模态 API key:  nano $SKILL_DIR/.env"
    print_info "  2. 配置 tikhub:                 nano ~/.claude/.env"
    print_info "  3. 重启 Claude Code 让 skill 生效"
    print_info "  4. 直接对 Claude 说："找对标 / 拆这条爆款 / 对着这条仿写""
    echo ""
    print_info "冒烟测试（可选）："
    print_info "  tikhub --health"
    print_info "  tikhub list xiaohongshu search"
    echo ""
}

trap 'print_error "安装过程出错"; exit 1' ERR

main
