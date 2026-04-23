# social-account-doctor

> 小红书 / 抖音 / 快手 / 视频号 / B 站 自媒体「**(素材打底 →) 找对标 → 拆爆款 → 套自己**」四命令闭环。
> 输入我的账号 / 选题方向 / 原始素材 → 输出**可发的下一条笔记初稿**（标题 + 封面大字 + 首段 + CTA）。
> Claude Code Skill / OpenClaw Skill。

<p align="center">
  <img src="docs/images/demo-page-01.png" width="32%" alt="TL;DR — 这条会爆吗？">
  <img src="docs/images/demo-page-04.png" width="32%" alt="六维拆解评分">
  <img src="docs/images/demo-page-05.png" width="32%" alt="三图 multimodal 封面诊断">
</p>

> 📄 上图来自 `reports/xhs-22029ddb-20260422-1410.pdf` — 对一条真实小红书笔记跑完 crack 后的成品报告（7 页 A4，思源 + 卡片 CSS）。完整 md/html/pdf 三件套都在 `reports/`。

## ✨ 特性

- 🎯 **四命令闭环**：`compose`（素材打底）→ `find`（多模态识别本质 + 矩阵搜 + 相似度过滤）→ `crack`（钩子/骨架/封面/标签 4 行拆）→ `adapt`（3 标题 + 3 封面大字 + 1 首段 + 1 CTA）
- 🧬 **找对标靠本质、不靠关键词**：单搜「东北大酱」会出一堆真人主播 — 5 维抽象 + 矩阵词 + 多模态相似度过滤，才能找到"AI 拟人 + 怀旧 + 反差"的真同行
- 🌐 **5 个平台统一入口**：xiaohongshu / douyin / kuaishou / wechat (公众号 + 视频号) / bilibili，走 tikhub HTTP CLI，零 MCP 工具污染
- 🖼 **多模态原生**：封面 → 5 变量 + 模板归类（A 大字报 / D 实物展示 …）；视频 → talking / visual / keyframe 三模式自动路由；后台截图 → 结构化指标
- 📋 **可发即产**：输出不是"建议"，是**能直接粘到 App 发送框的初稿**（含数字、人群锚定、CTA）
- 📄 **按需 md → PDF**：`scripts/build_report_pdf.py` 一键生成思源字体 + A4 + 卡片 CSS 的打印版
- 🩺 **诊断模式是兜底**：用户问「为什么不爆」才走 `references/diagnostic-mode.md`，不是默认路径

## 📸 案例演示 — 一条真实小红书笔记跑完 crack

一条 AI 赛道的新笔记（`@AI折腾日记 / 「GPT image2效果太爆炸了！」`），发布 21 分钟，3 赞 1 评 2 收藏。跑完 crack 得出：**9 成扑街概率、3 个一票否决项、可在 5 分钟内抢救的 P0 行动。**

### 1. L2 同赛道对标扫描 — 找到"真对标"而不是"同关键词"

<p align="center">
  <img src="docs/images/demo-page-03.png" width="72%" alt="L2 同赛道 top 10 扫描">
</p>

> 赛道特征自动归纳：头部 2k+ 赞已成型、收藏比 ≥ 0.5（干货教程）、评论 50-200 是常态。用户这条"无差异化跟风"被直接定位。

### 2. 封面三图 multimodal 拆解 — 钩子被埋到第 3 张

<p align="center">
  <img src="docs/images/demo-page-05.png" width="72%" alt="三图 multimodal 封面诊断">
</p>

> `scripts/analyze_image.py` 跑完三张封面 → 第 1 张判定为 D 实物展示型（0 钩子）、第 3 张才是 A 大字报型 + 人群锚定「设计师又又又要失业了」。**封面顺序反了 → 小红书 CTR 只看第 1 张 → 直接判死刑。**

### 3. 行动清单 — 不是"建议"，是可粘贴的改写

<p align="center">
  <img src="docs/images/demo-page-06.png" width="72%" alt="P0/P1/P2 行动清单">
</p>

> P0（5 分钟内）：把第 3 张设成封面 + 正文补提示词 + 标题按公式 1（数字+人群+效果）重写，直接给出 3 个候选。P1/P2 覆盖 24h 互动钩 + 账号月度转型。

## 🚀 一键安装

```bash
git clone https://github.com/JuneYaooo/social-account-doctor.git
cd social-account-doctor
bash install_as_skill.sh
```

脚本会拷贝到 `~/.claude/skills/social-account-doctor/`、装 Python 依赖、把 `tikhub` 软链进 `~/.local/bin/`。Claude Code 重启后自动识别。

## ⚙ 配置

### 1. tikhub HTTP CLI（数据来源）

```bash
# 申请 key: https://tikhub.io/
mkdir -p ~/.claude
echo 'TIKHUB_API_KEY=YOUR_KEY' >> ~/.claude/.env
chmod 600 ~/.claude/.env

tikhub --health                       # {"status":"healthy",...}
tikhub list xiaohongshu search        # 看可用工具
```

**已缓存 5 平台**（开箱即用）：`xiaohongshu` / `douyin` / `kuaishou` / `wechat` / `bilibili`。追加 `tiktok` / `weibo` / `youtube` / `zhihu` 等：`python3 tikhub/scripts/refresh_tools.py tiktok`。

> 💡 **为什么不用 `claude mcp add`**：4 个平台合计会注入 ~370 个 `mcp__tikhub-*__*` 到全局工具列表，污染所有无关任务。HTTP CLI 方式：所有平台共用一个 key、零工具列表污染、不用重启 claude。详见 `tikhub/README.md`。

### 2. 多模态分析（封面 / 视频 / 截图）

编辑 `~/.claude/skills/social-account-doctor/.env`：

```bash
# Gemini 3.1 Pro (OpenAI 兼容协议) — 封面 / 视频 / 截图都用它
VIDEO_ANALYSIS_API_KEY=sk-xxx
VIDEO_ANALYSIS_BASE_URL=https://your-gemini-proxy.com/v1
VIDEO_ANALYSIS_MODEL_NAME=gemini-3-pro

# SenseVoice / Whisper — 仅视频 talking 模式需要
AUDIO_TRANSCRIPTION_API_KEY=sk-xxx
AUDIO_TRANSCRIPTION_BASE_URL=https://your-asr-proxy.com/v1
AUDIO_TRANSCRIPTION_MODEL=sensevoice
```

> 🔒 **安全**：脚本只读 skill 目录下的 `.env` 和 `~/.claude/.env`，**不会**向上递归抓项目 `.env`，避免误吃无关密钥。

### 3. 系统依赖

Python 3.10+，ffmpeg（`apt install ffmpeg` / `brew install ffmpeg`）。

## 🛠 在 Claude Code 里怎么用

直接和 Claude 说：

| 你说 | Claude 走哪条 |
|---|---|
| "找对标" / "扫一下同赛道" + 我的账号链接 | **find** |
| "拆这条爆款" + 笔记/视频链接 | **crack** |
| "对着这条仿写" / "下一条该怎么写" | **crack + adapt** |
| "我有素材（文档/图片/视频），帮我写一条能爆的" | **compose + find + crack + adapt**（全闭环） |
| "我这个号缺爆款选题" | **find + crack + adapt** |
| "为什么我这条不爆" / "完整诊断" | L2 兜底诊断（按需，不主推） |

### find 的 5 步（关键差异）

| Step | 干什么 | 不能省 |
|---|---|---|
| 1 | 多模态识别我的"内容本质"（5 个抽象维度，不是表面词） | 必须 |
| 2 | 5 维交叉生成 4-6 个搜索词矩阵（**禁止单关键词**） | 必须 |
| 3 | 矩阵词并行 search → 候选池 20-50 条 | 必须 |
| 4 | 候选池每条多模态过相似度（≥ 3 维相似才留） | 必须（省了 = 表面假对标污染） |
| 5 | 体量 + 活跃度过滤 → 5-10 真对标 → 人工勾 3-5 条 | 必须 |

## 📂 输出位置

跑完闭环，文件落到当前工作目录：

```
./reports/
  {YYYYMMDD-HHMM}-find-{我的账号末8位}.md      # 5-10 对标 + 为什么是真对标
  {YYYYMMDD-HHMM}-crack-{对标末8位}.md         # 每条 4 行清单
  {YYYYMMDD-HHMM}-adapt-{选题短码}.md          # 标题 + 封面 + 首段 + CTA → 可发

./assets/                                     # 副产品，跨任务累积
  hooks-xhs.md / hooks-douyin.md / hooks-kuaishou.md / hooks-wechat-channels.md
```

> 💡 `.gitignore` 加 `reports/`（含账号选题信息，通常不想 commit），`assets/` 是长期资产建议 commit。

### 按需把 md 打成 PDF

```bash
python3 scripts/render_report_pdf.py reports/xhs-xxx.md
# → reports/xhs-xxx.pdf  (思源字体 + A4 + 卡片 CSS)
```

## 📦 仓库结构

```
social-account-doctor/
├── SKILL.md                            # L1 主入口 — Claude 加载这个（四命令 SOP）
├── install_as_skill.sh                 # 一键安装到 ~/.claude/skills/
├── references/
│   ├── scoring-vocab.md                # L3 评分词典（5 封面 / 10 标题 / 3 骨架 / 7 钩子）
│   ├── diagnostic-mode.md              # L2 兜底诊断（"为什么不爆"才走这里）
│   └── platforms/                      # 平台阈值数据（被 L2 调用）
│       └── xiaohongshu.md / douyin.md / kuaishou.md / wechat-channels.md / bilibili.md
├── scripts/
│   ├── analyze_document.py             # 文档/图片/视频素材 → compose 独家要素溯源
│   ├── analyze_image.py                # 封面 → 5 变量 + 模板归类 + 钩子识别
│   ├── analyze_video.py                # 视频 → talking/visual/keyframe 三模式自动路由
│   ├── ocr_screenshot.py               # 后台截图 → 结构化指标
│   ├── dispatch_account.py             # 账号链接 → platform + user_id + tikhub 命令
│   └── render_report_pdf.py            # md → A4 卡片 PDF（思源字体）
└── tikhub/                             # 自包含 tikhub HTTP CLI
    ├── bin/tikhub                      # CLI 入口
    ├── lib/tikhub_client.py            # HTTP JSON-RPC + SSE + session（纯 stdlib）
    ├── references/tools-{平台}.json    # 5 平台工具目录缓存
    └── scripts/refresh_tools.py        # 重建工具目录
```

## ⚠ 数据时效性

`references/platforms/*.md` 里所有阈值（完播率 / CTR / CES 等）均为**行业经验值**，**非平台官方公告**。

📅 **采集日期：2026-04** ｜ **建议复核：每 6 个月**

主流程（find/crack/adapt）**不依赖这些数字** — 只用作 L2 诊断时的方向判断。

## 🧭 内容层铁律

**脚本层（tikhub 返回的 JSON / 多模态分析输出）信任直接吐；账号资料层（定位、简介、人设）不清楚的地方宁可不说也不编。** 详见 `SKILL.md` 开头铁律。

## 🙏 致谢

- [tikhub.io](https://tikhub.io/) — 16 平台统一 HTTP API，本仓库数据层基座
- [lewislulu/html-ppt-skill](https://github.com/lewislulu/html-ppt-skill) — Claude Code skill SKILL.md frontmatter 写法参考
- [JuneYaooo/gpt-image2-ppt-skills](https://github.com/JuneYaooo/gpt-image2-ppt-skills) — README / install 脚本 / 仓库骨架参考

## License

MIT © 2026 JuneYaooo
