# social-account-doctor

> 小红书 / 抖音 / 快手「账号 + 内容」诊断引擎 — 截图 / 链接进，**「卡在哪一层 + 怎么调」** 的可执行报告出。

**不是** "AI 看了下你的账号觉得还行"，**是** **平台专属阈值 × 对标差距 × 可抄模板** 的三段式判决书。

## 它能做什么

| 输入 | 产出 |
|---|---|
| **一张笔记后台数据截图** | 漏斗自检 + 短板定位 + P0 行动清单 |
| **截图 + 笔记/视频链接** | + 多模态拆解封面/视频 + CES 健康度 + 关键词搜索诊断 |
| **账号链接（自己 + 对标）** | + 6 维评分 + 同赛道差距矩阵 + 可抄清单 |
| **只给账号链接（没对标）** | 自动按"5k-50k 粉、同赛道、活跃"找候选 |

覆盖三平台两大主诊断逻辑：
- **抖音**：5s 完播率（行业合格线 ~50%）+ 钩子诊断（前 3 帧 + 首句口播）
- **小红书**：CES + 封面 CTR + 搜索分发（COO 公开"近 70% 月活有搜索行为"）
- **快手**：完播 + 关注转化率（老铁经济）+ 同城 + 评论质量

---

## 怎么用

这个 repo 是一个 **Claude Code skill**，挂载后用自然语言触发：

```
"帮我诊断这条笔记" + 截图 + 链接
"看看我这个号该往哪个方向调" + 主页链接
"我和这个对标账号差在哪" + 两个链接
"帮我找几个对标账号分析" + 我方账号链接
```

Claude 会自动跑：**输入路由 → tikhub 数据抓取 → Gemini 多模态拆解 → 三层诊断 → 行动建议**。

---

## 安装

### 1. 克隆为 Claude Code skill

```bash
git clone https://github.com/JuneYaooo/social-account-doctor.git \
  ~/.claude/skills/account-diagnostic
```

### 2. 配置 tikhub MCP（数据来源）

申请 key：https://tikhub.io/

在 Claude Code `settings.json` 的 `mcpServers` 里添加（任选你需要的平台）：

```json
{
  "mcpServers": {
    "tikhub-douyin": {
      "type": "http",
      "url": "https://mcp.tikhub.io/douyin/mcp",
      "headers": { "Authorization": "Bearer YOUR_TIKHUB_KEY" }
    },
    "tikhub-xiaohongshu": {
      "type": "http",
      "url": "https://mcp.tikhub.io/xiaohongshu/mcp",
      "headers": { "Authorization": "Bearer YOUR_TIKHUB_KEY" }
    },
    "tikhub-kuaishou": {
      "type": "http",
      "url": "https://mcp.tikhub.io/kuaishou/mcp",
      "headers": { "Authorization": "Bearer YOUR_TIKHUB_KEY" }
    }
  }
}
```

### 3. 配置多模态分析（封面 / 视频 / 截图 OCR）

复制 `.env.example` 为 `.env` 并填入：

```bash
# Gemini 3.1 Pro（OpenAI 兼容协议代理）— 视觉 / 视频 / 截图 OCR 都用它
VIDEO_ANALYSIS_API_KEY=sk-xxx
VIDEO_ANALYSIS_BASE_URL=https://your-gemini-proxy.com/v1
VIDEO_ANALYSIS_MODEL_NAME=gemini-3-pro

# SenseVoice / Whisper 兼容协议 — 仅 talking 模式（口播视频转写）需要
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

---

## 仓库结构

```
social-account-doctor/
├── SKILL.md               # 主入口 — Claude 加载这个
├── platforms/             # 三大平台子手册（阈值 + 工具映射 + 6 维评分细则）
│   ├── xiaohongshu.md
│   ├── douyin.md
│   └── kuaishou.md
└── scripts/               # 多模态分析脚本
    ├── ocr_screenshot.py    # 后台截图 → 结构化指标
    ├── dispatch_account.py  # 账号链接 → platform + user_id
    ├── analyze_image.py     # 封面 / 首帧 → 5 变量 + 模板归类 + 钩子
    └── analyze_video.py     # 视频 → talking / visual / keyframe 三模式自动路由
```

---

## 数据时效性说明

本 skill 内所有平台阈值（完播率 / CTR / CES / 互动率等）均为**行业经验值**（蝉妈妈 / 千瓜 / 新红 / COO 公开发言等多源），**非平台官方公告**。

📅 **数据采集日期：2026-04 / 建议复核周期：6 个月**

每个 `platforms/*.md` 顶部都有"数据来源"小节，列出原始链接。诊断时用作"方向判断"，**不是"绝对死线"**。

---

## License

MIT © 2026 JuneYaooo

---

## 反馈与贡献

- 数字漂移上报：[Issues](https://github.com/JuneYaooo/social-account-doctor/issues)
- 平台 API 失效：[Issues](https://github.com/JuneYaooo/social-account-doctor/issues)
- PR 欢迎，特别是新平台的子手册（B 站 / 视频号 / 公众号）
