# social-account-doctor — Agent 自助安装指南

> 这份文件是**给 AI agent 读的**。用户把它的 URL 丢给你(Claude Code / OpenClaw / Codex / Cursor / Trae / Hermes Agent 等),你照着做即可完成安装。

## 你要做的事

1. **Clone 仓库**到用户当前工作目录(或 `~/src/` 之类合理位置):
   ```bash
   git clone --depth 1 https://github.com/JuneYaooo/social-account-doctor.git
   cd social-account-doctor
   ```
   `--depth 1` 只拉最新快照，国内网络下明显更快更稳。

2. **按 agent 宿主跑安装脚本**:
   ```bash
   # Claude Code（默认，兼容旧用法）
   bash install_as_skill.sh --target claude

   # Codex / Cursor / OpenClaw 三选一
   bash install_as_skill.sh --target codex
   bash install_as_skill.sh --target cursor
   bash install_as_skill.sh --target openclaw
   ```
   已在虚拟环境中安装依赖或做离线安装时，可追加 `--skip-deps`；正常安装不要跳过。
   脚本会:
   - 把仓库内容拷贝到对应宿主的 skills 目录
   - 安装 Python 依赖(`pip install -r requirements.txt`)
   - 软链 `tikhub` CLI
   - 交互式引导配置 `.env`

3. **帮用户填 key**(脚本会问,但你也可以提前跟用户确认):

   | key | 必选? | 用途 | 去哪搞 |
   |---|---|---|---|
   | `VIDEO_ANALYSIS_API_KEY` + `VIDEO_ANALYSIS_BASE_URL` | ✅ 必选 | 看图 / 看视频的多模态大模型（OpenAI 兼容协议） | 用户自己的 key 或代理站 |
   | `TIKHUB_API_KEY` | ⚪ 可选（付费） | 量大 / 需要视频号时的平台数据抓取（五平台全支持） | https://tikhub.io/ |
   | `AUDIO_TRANSCRIPTION_API_KEY` | ⚪ 可选 | 拆"真人口播"视频时做语音转写 | SiliconFlow / OpenAI 兼容服务 |

   key 写到安装后的 `social-account-doctor/.env`（脚本从 `.env.example` 自动创建）。

   **平台数据源优先级（越高越像真人、越安全）**：① agent 自带 computer use / 浏览器工具直接访问平台页面（首选，零配置）→ ② opencli → ③ TikHub API（付费、稳定、结构化 JSON，五平台全支持含视频号；要用时配 `TIKHUB_API_KEY`）→ ④ mc 扫码登录（**最后手段**：上游 MediaCrawler 反爬加剧、账号风控风险最高，仅当 ①-③ 都不可用时让 agent 跑 `mc --setup`，详见 `mediacrawler/README.md`）。宿主没有浏览器能力时 agent 会和用户确认用哪档。

4. **确认系统依赖**:
   - Python 3.10+
   - `ffmpeg` —— Linux: `apt install ffmpeg`,macOS: `brew install ffmpeg`

5. **提示用户重启当前 agent 宿主**,skill 才会被识别。

## 装完怎么验证

让用户说一句「帮我扫一下 [小红书账号链接] 的同赛道」：
- 如果 Claude 先**问一句用 TikHub 还是扫码登录（mc）**，然后按选择路由到 `find` 命令抓数据，就装好了；
- 只配了一种数据源时 Claude 会直接用可用的那种并告知，同样算装好。

## 如果用户已经装过

`install_as_skill.sh` 会检测目标 Skill 目录是否存在并询问是否覆盖。覆盖不会丢 `.env`（脚本会保留）。

## 慢网（中国大陆直连）加速

安装链路的所有下载源都会**自动探测选最快**，正常情况下你不需要做任何事：

| 下载内容 | 自动择优策略 |
|---|---|
| pip 依赖（`install_as_skill.sh` 和 `mc --setup`） | 官方 PyPI / 清华 / 阿里镜像探测选最快 |
| MediaCrawler 克隆 | github 直连（重试 2 次）→ gh 代理镜像回退 |
| Playwright Chromium（约 200MB） | 官方 CDN vs npmmirror 镜像，镜像明显更快才启用 |

用户环境变量永远优先于自动探测；有代理时 `export HTTPS_PROXY=...` 对 git/pip/playwright 全部生效。遇到特殊网络想强制指定时：

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple   # 强制 pip 源
PLAYWRIGHT_DOWNLOAD_HOST=https://registry.npmmirror.com/-/binary/playwright  # 强制 Chromium 源
MC_GIT_URL=https://gh-proxy.com/https://github.com/NanmiCoder/MediaCrawler.git  # 强制克隆地址
mc --setup --no-mirror                                    # 或整体禁用镜像，全部直连官方源
```

`mc --setup` 的依赖装的是裁剪版 `mediacrawler/requirements-lean.txt`（砍掉 webui/测试/迁移类包），自检不过会自动回退上游全量 requirements，无需干预。

## 不要做的事

- ❌ 不要把 key 提交进仓库；写到安装后 Skill 自己的 `.env`
- ❌ 不要改 `SKILL.md` 的 `name` / `description` frontmatter,那是 agent 识别入口
- ❌ 不要用 `sudo` 跑安装脚本
