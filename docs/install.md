# social-account-doctor — Agent 自助安装指南

> 这份文件是**给 AI agent 读的**。用户把它的 URL 丢给你(Claude Code / OpenClaw / Codex / Cursor / Trae / Hermes Agent 等),你照着做即可完成安装。

## 你要做的事

1. **Clone 仓库**到用户当前工作目录(或 `~/src/` 之类合理位置):
   ```bash
   git clone https://github.com/JuneYaooo/social-account-doctor.git
   cd social-account-doctor
   ```

2. **跑安装脚本**:
   ```bash
   bash install_as_skill.sh
   ```
   脚本会:
   - 把仓库内容拷贝到 `~/.claude/skills/social-account-doctor/`
   - 安装 Python 依赖(`pip install -r requirements.txt`)
   - 软链 `tikhub` CLI
   - 交互式引导配置 `.env`

3. **帮用户填 3 个 key**(脚本会问,但你也可以提前跟用户确认):

   | key | 必选? | 用途 | 去哪搞 |
   |---|---|---|---|
   | `TIKHUB_API_KEY` | ✅ 必选 | 抓小红书/抖音/快手/视频号/B 站 数据 | https://tikhub.io/ |
   | `OPENAI_API_KEY` + `OPENAI_BASE_URL` | ✅ 必选 | 看图 / 看视频的多模态大模型(推荐 Gemini 3.1 Pro,OpenAI 协议兼容中转站都行) | 用户自己的 key 或代理站 |
   | `SENSEVOICE_API_KEY` 或 `WHISPER_API_KEY` | ⚪ 可选 | 拆"真人口播"视频时做语音转写 | SiliconFlow / OpenAI |

   key 写到 `~/.claude/skills/social-account-doctor/.env`(脚本自动创建)。

4. **确认系统依赖**:
   - Python 3.10+
   - `ffmpeg` —— Linux: `apt install ffmpeg`,macOS: `brew install ffmpeg`

5. **提示用户重启 Claude Code**(或当前 agent 宿主),skill 才会被识别。

## 装完怎么验证

让用户说一句「帮我扫一下 [小红书账号链接] 的同赛道」,如果 Claude 能路由到 `find` 命令并调 tikhub 抓数据,就装好了。

## 如果用户已经装过

`install_as_skill.sh` 会检测 `~/.claude/skills/social-account-doctor/` 是否存在并询问是否覆盖。覆盖不会丢 `.env`(脚本会保留)。

## 不要做的事

- ❌ 不要把 key 写到 `~/.claude/skills/social-account-doctor/` 之外的任何 `.env`(skill 只读这一个)
- ❌ 不要改 `SKILL.md` 的 `name` / `description` frontmatter,那是 agent 识别入口
- ❌ 不要用 `sudo` 跑安装脚本
