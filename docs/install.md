# social-account-doctor — Agent 自助安装指南

> 这份文件是**给 AI agent 读的**。用户把它的 URL 丢给你(Claude Code / OpenClaw / Codex / Cursor / Trae / Hermes Agent 等),你照着做即可完成安装。

## 你要做的事

1. **Clone 仓库**到用户当前工作目录(或 `~/src/` 之类合理位置):
   ```bash
   git clone https://github.com/JuneYaooo/social-account-doctor.git
   cd social-account-doctor
   ```

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

3. **帮用户填 3 个 key**(脚本会问,但你也可以提前跟用户确认):

   | key | 必选? | 用途 | 去哪搞 |
   |---|---|---|---|
   | `TIKHUB_API_KEY` | ✅ 必选 | 抓小红书/抖音/快手/视频号/B 站 数据 | https://tikhub.io/ |
   | `VIDEO_ANALYSIS_API_KEY` + `VIDEO_ANALYSIS_BASE_URL` | ✅ 必选 | 看图 / 看视频的多模态大模型（OpenAI 兼容协议） | 用户自己的 key 或代理站 |
   | `AUDIO_TRANSCRIPTION_API_KEY` | ⚪ 可选 | 拆"真人口播"视频时做语音转写 | SiliconFlow / OpenAI 兼容服务 |

   key 写到安装后的 `social-account-doctor/.env`（脚本从 `.env.example` 自动创建）。

4. **确认系统依赖**:
   - Python 3.10+
   - `ffmpeg` —— Linux: `apt install ffmpeg`,macOS: `brew install ffmpeg`

5. **提示用户重启当前 agent 宿主**,skill 才会被识别。

## 装完怎么验证

让用户说一句「帮我扫一下 [小红书账号链接] 的同赛道」,如果 Claude 能路由到 `find` 命令并调 tikhub 抓数据,就装好了。

## 如果用户已经装过

`install_as_skill.sh` 会检测目标 Skill 目录是否存在并询问是否覆盖。覆盖不会丢 `.env`（脚本会保留）。

## 不要做的事

- ❌ 不要把 key 提交进仓库；写到安装后 Skill 自己的 `.env`
- ❌ 不要改 `SKILL.md` 的 `name` / `description` frontmatter,那是 agent 识别入口
- ❌ 不要用 `sudo` 跑安装脚本
