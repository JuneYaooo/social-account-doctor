# social-account-doctor

> 小红书 / 抖音 / 快手 / 视频号 自媒体「**找对标 → 拆爆款 → 套自己**」三命令闭环。
> 输入我的账号 / 选题方向 → 输出**可发的下一条笔记初稿**（标题 + 封面大字 + 首段 + CTA）。

**不写诊断报告**（那是兜底）。**不挖钩子建仓库**（那是副产品）。
直接对着具体爆款，告诉你下一条该怎么写。

> **平台覆盖度**：小红书 ✅ / 抖音 ✅ / 快手 ✅ / 视频号 ✅ / B 站 ✅
> （v0.4.0：B 站加入 + 自包含 tikhub HTTP CLI；v0.2.5：视频号 user_search 503 fallback / 冷启失败号判定 / 赛道错位诊断；视频号没有可分享的链接/ID，入口只能走账号名搜索 — 详见 SKILL.md §7「视频号独立路径」）。

---

## 闭环

```
[我的账号 / 选题方向]
       │
       ▼ ① find  (多模态识别本质 → 矩阵搜 → 相似度过滤 → 人工勾选)
[5-10 个真对标爆款]
       │
       ▼ ② crack  (每条 4 行：钩子 / 骨架 / 封面 / 标签)
[可抄元素清单]
       │
       ▼ ③ adapt  (3 标题 + 3 封面大字 + 1 首段 + 1 CTA)
[我的下一条笔记初稿]  →  发布  →  数据回收
```

---

## 三个命令在 Claude 里怎么用

| 你说 | Claude 走哪条 |
|---|---|
| "找对标"/"扫一下同赛道" + 我的账号链接 | **find** |
| "拆这条爆款" + 笔记/视频链接 | **crack** |
| "对着这条仿写" / "下一条该怎么写" | **crack + adapt** |
| "我想发 XX 主题，缺爆款选题" | **find + crack + adapt**（全闭环） |
| "为什么我这条不爆"/"完整诊断" | L2 兜底诊断（按需，不主推） |

---

## find 的 5 步（关键差异）

| Step | 干什么 | 不能省 |
|---|---|---|
| 1 | 多模态识别我的"内容本质"（5 个抽象维度，不是表面词） | 必须 |
| 2 | 5 维交叉生成 4-6 个搜索词矩阵（**禁止单关键词**） | 必须 |
| 3 | 矩阵词并行 search → 候选池 20-50 条 | 必须 |
| 4 | 候选池每条多模态过相似度（≥ 3 维相似才留） | 必须（这一步省了 = 表面假对标污染） |
| 5 | 体量 + 活跃度过滤 → 5-10 个真对标 → 人工勾 3-5 条 | 必须 |

**为什么这样**：单搜"东北大酱"会出一堆真人主播，和 AI 萌宠橘猫做大酱**形不像神不像**。本质识别才能找到"AI 拟人 + 怀旧 + 反差"的真同行。

---

## 安装

### 1. 克隆为 Claude ​Code skill

```bash
git clone https://github.com/JuneYaooo/social-account-doctor.git \
  ~/.claude/skills/social-account-doctor
```

### 2. 配置 tikhub HTTP CLI（数据来源）

申请 key：https://tikhub.io/

本仓库**自包含 tikhub CLI**（在 `tikhub/` 目录），不依赖任何外部 skill。`git clone` 之后单独装就能跑。

```bash
cd ~/.claude/skills/social-account-doctor

# 1. API key 写到 ~/.claude/.env (chmod 600)
mkdir -p ~/.claude
cat >> ~/.claude/.env <<'EOF'
TIKHUB_API_KEY=YOUR_TIKHUB_KEY
EOF
chmod 600 ~/.claude/.env

# 2. 让 tikhub 命令在 PATH（bash + fish 都能用）
ln -sf "$(pwd)/tikhub/bin/tikhub" ~/.local/bin/tikhub

# 3. 验证
tikhub --health     # {"status":"healthy",...}
tikhub list xiaohongshu search    # 看可用工具
```

**调用形式**：`tikhub <platform> <tool> --key1 value1 --key2 value2`（或 `--json '{"k":"v"}'`）

**已缓存平台**（5 个，开箱即用）：`xiaohongshu` / `douyin` / `kuaishou` / `wechat` / `bilibili`

**追加平台**（tikhub 还支持 `tiktok` / `instagram` / `weibo` / `youtube` / `zhihu` 等 9 个）：
```bash
python3 tikhub/scripts/refresh_tools.py tiktok    # 拉缓存
tikhub list tiktok                                # 验证
```

详见 [`tikhub/README.md`](tikhub/README.md) — 包含协议细节、错误排查、调试模式。

> 💡 **为什么不用 `claude mcp add`**：之前每个平台单独 `claude mcp add` 会注入几十~上百个 `mcp__tikhub-*__*` 工具到全局工具列表（4 个平台合计 ~370 个），污染所有跟自媒体无关的任务。HTTP CLI 方式：所有平台共用一个 key、一个 wrapper、零工具列表污染、不需要重启 claude。

> ⚠️ **降级方案（紧急回退）**：如果 wrapper 临时挂了，可以暂用 `claude mcp add tikhub-xxx -- npx mcp-remote https://mcp.tikhub.io/<plat>/mcp --header "Authorization: Bearer <key>"` + 重启 claude 的方式。但这是临时措施，用完 `claude mcp remove`，不要常驻。

### 3. 配置多模态分析

复制 `.env.example` 为 `.env`：

```bash
# Gemini 3.1 Pro (OpenAI 兼容协议) — 封面/视频/截图都用它
VIDEO_ANALYSIS_API_KEY=sk-xxx
VIDEO_ANALYSIS_BASE_URL=https://your-gemini-proxy.com/v1
VIDEO_ANALYSIS_MODEL_NAME=gemini-3-pro

# SenseVoice / Whisper — 仅视频 talking 模式需要
AUDIO_TRANSCRIPTION_API_KEY=sk-xxx
AUDIO_TRANSCRIPTION_BASE_URL=https://your-asr-proxy.com/v1
AUDIO_TRANSCRIPTION_MODEL=sensevoice
```

### 4. 系统依赖

- Python 3.10+
- ffmpeg（`brew install ffmpeg` / `apt install ffmpeg`）

```bash
pip install -r requirements.txt
```

### 5. 验证安装

```bash
python3 scripts/analyze_image.py path/to/any.jpg
# 在 Claude 里说"搜小红书 测试" — 能返回结果即 tikhub CLI OK
```

---

## 输出位置

完整闭环跑完，文件落到当前工作目录：

```
./reports/
  {YYYYMMDD-HHMM}-find-{我的账号末8位}.md      # 5-10 对标 + 为什么是真对标
  {YYYYMMDD-HHMM}-crack-{对标末8位}.md         # 每条 4 行清单
  {YYYYMMDD-HHMM}-adapt-{选题短码}.md          # 标题 + 封面 + 首段 + CTA → 可发

./assets/                                     # 副产品，跨任务累积
  hooks-xhs.md / hooks-douyin.md / hooks-kuaishou.md / hooks-wechat-channels.md
```

**建议**在你项目的 `.gitignore` 加 `reports/` — 报告里通常含账号/选题信息，不一定想 commit。
`assets/` 是你长期资产，建议 commit 进去。

---

## 仓库结构

```
social-account-doctor/
├── SKILL.md                            # L1 主入口 — Claude 加载这个（三命令 SOP）
├── references/
│   ├── scoring-vocab.md                # L3 评分词典（5 封面 / 10 标题 / 3 骨架 / 7 钩子）
│   ├── diagnostic-mode.md              # L2 兜底诊断（"为什么不爆"才走这里）
│   └── platforms/                      # 平台阈值数据（被 L2 调用）
│       └── xiaohongshu.md / douyin.md / kuaishou.md / wechat-channels.md / bilibili.md
├── scripts/                            # 多模态 + 路由脚本
│   ├── analyze_image.py                # 封面 → 5 变量 + 模板归类 + 钩子识别
│   ├── analyze_video.py                # 视频 → talking/visual/keyframe 三模式自动路由
│   ├── ocr_screenshot.py               # 后台截图 → 结构化指标
│   └── dispatch_account.py             # 账号链接 → platform + user_id + tikhub CLI 命令
└── tikhub/                             # 自包含 tikhub HTTP CLI（v0.4.0 加入）
    ├── README.md                       # CLI 用法 + 协议细节
    ├── bin/tikhub                      # CLI 入口（chmod +x）
    ├── lib/tikhub_client.py            # HTTP JSON-RPC + SSE + session 管理（纯 stdlib）
    ├── references/tools-{平台}.json    # 5 平台工具目录缓存（~330KB）
    └── scripts/refresh_tools.py        # 重建工具目录
```

---

## 数据时效性

`references/platforms/*.md` 里所有阈值（完播率 / CTR / CES 等）均为**行业经验值**，**非平台官方公告**。

📅 **采集日期：2026-04**｜**建议复核：每 6 个月**

主流程（find/crack/adapt）**不依赖这些数字** — 只用作 L2 诊断时的方向判断。

---

## License

MIT © 2026 JuneYaooo

---

## 反馈与贡献

- Issues：https://github.com/JuneYaooo/social-account-doctor/issues
- 数字漂移上报 / 平台 API 失效 / 新平台贡献（B 站 / 公众号专项）都欢迎
