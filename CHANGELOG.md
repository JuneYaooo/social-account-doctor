# Changelog

## v0.2.5 — 2026-04-21

实战拆解视频号「哈吉老猫」暴露三个空洞 → 全部沉淀进文档。

### 新增 — 视频号一等公民支持（之前是占位）

- **SKILL.md §7 加「视频号独立路径」子表**：视频号客户端**根本不输出可分享的链接 / 视频 ID**（只能卡片分享），所以入口流程跟其他三平台完全不同。原 §7 工具速查只有小红书/抖音/快手 3 列，视频号用户搜索/视频详情等核心工具未列出。现在补齐。
- **SKILL.md §3 Step 3 工具表加视频号**：双源对比（`search_ordinary` 综合 + `search_latest` 最新）—— 交集 = 已被算法验证爆款，差集 = 蓝海窗口。
- **README 顶部定位 + MCP 配置 + assets 列表 + 仓库结构图**：四处全部补齐视频号。MCP 配置改用 `claude mcp add` CLI 命令格式（更直接，避免编辑 settings.json 出错），同时保留 settings.json 写法作为 fallback。

### 新增 — `references/platforms/wechat-channels.md` §4 大改

之前 §4 工具映射全是 `mcp__tikhub-wechat__*` 占位符，**没有真实工具名** — 拿到这文件根本不知道调哪个。本版改写：

- **§4.0 工具一览表**：13 个工具的真实名 + ✅/🟡/❌ 稳定性标记（实测 2026-04-21）
- **§4.2 user_search 503 兜底流程**：`user_search` 是 tikhub-wechat 里**最不稳定**的接口（实测 2026-04 高频 503），新增 4 步 fallback —— 用 `_search_ordinary(账号名)` + nickname 完全相等 + iconUrl 一致性双重校验，跳过 user_search 直接进诊断。
- **§4.3 冷启失败号秒判公式**：`feed_count == 1` + 互动全 0 + 简介空，命中 3 项 = 冷启失败 → **单次 API 调用**就能出 P0 诊断。
- **§4.4 赛道错位诊断**：账号名暗示赛道（如"哈吉/哈基米/老猫"暗示猫梗）vs 实际内容错配 —— 视频号特有的死法。带实战案例「哈吉老猫」（21 天 0 互动 / AI 翻唱 vs 猫梗预期）。

### 新增 — SKILL.md §9 接口稳定性表分小节

- §9 改名「接口稳定性表」，原内容降为 **§9.1 小红书**
- 新增 **§9.2 视频号**：7 个接口的实测结果 + 5 条铁律（含 user_search 503 fallback、`feed_count==1 + 全0互动 = 冷启失败`、综合搜索结果"真号常常只有 1 条"的判定方法）
- 新增 **§9.3 抖音 / §9.4 快手**：标"待实测 2026-04-21"，附 `claude mcp add` 挂载命令模板。等下次会话挂上对应 MCP 后实测回填 v0.2.6

### 实测数据（本版未做的）

🟡 抖音、快手稳定性表是**占位**。本轮 SAD 升级时只挂载了 `tikhub-wechat` + `tikhub-xiaohongshu` MCP（按 memory 的"按需挂载"原则避免工具列污染），抖音/快手没现跑 ping。下次有人挂这俩 MCP 跑实战时把数据回填进 §9.3 §9.4 即可。

### 不再单独维护 wechat-search skill

之前 `~/.claude/skills/wechat-search/` 是独立 skill。本版起，所有视频号 / 公众号诊断经验**全部沉淀到 SAD 仓库**（`references/platforms/wechat-channels.md`），单点真相，避免分裂。wechat-search skill 保留作"轻量搜索/拆解工具"用途，但**生产闭环（找对标→拆爆款→套自己）一律走 SAD**。

---

## v0.2.4 — 2026-04-21

实战发现并修复:**小红书所有 V2 接口当前全挂,只用 V1**。整套 skill 内部口径不一致问题彻底解决。

### 修复 — 小红书接口稳定性（实证 2026-04-21）

实证结果（4 个搜索接口 × 笔记/用户两类 = 8 次 ping）:

| 工具 | 状态 |
|---|---|
| `xiaohongshu_app_search_notes` (App V1) | ✅ 稳 |
| `xiaohongshu_web_search_notes` (Web V1) | ✅ 稳 |
| `xiaohongshu_web_search_users` (Web V1) | ✅ 稳 |
| `xiaohongshu_app_v2_search_notes` (V2) | ❌ RetryError |
| `xiaohongshu_web_v2_fetch_search_notes` (V2) | ❌ RetryError |
| `xiaohongshu_app_v2_search_users` (V2) | ❌ RetryError |
| `xiaohongshu_web_v2_fetch_search_users` (V2) | ❌ RetryError |
| `xiaohongshu_app_search_users` (App V1) | ❌ RetryError（特例） |

**根因**：原 skill 内部口径不一致 — SKILL.md 写"V1 优先",但 `references/platforms/xiaohongshu.md` 和 `scripts/dispatch_account.py` 都默认 V2; platforms 里还有"V2 失败切 web V2"的过时建议。诊断时容易误判"接口全挂"。

### 改动

- **SKILL.md 新增 §9 接口稳定性表** — 集中维护小红书可用/禁用接口清单 + 实测日期 + 复核周期（每月一次）。这是未来的唯一真相源。
- **SKILL.md §3 / §7 接口名修正**：搜索默认 `xiaohongshu_app_search_notes`(V1),不再标"V2 fallback"
- **`references/platforms/xiaohongshu.md`** 重写过时硬规则（删掉"V2 失败切 web V2"），fallback 表 search_notes / search_users 全改 V1
- **`references/diagnostic-mode.md`** 4 处接口名 V2 → V1
- **`scripts/dispatch_account.py`** 路由 search_notes V2→App V1,search_users V2→Web V1

### 新增 — 限流注释

- **当前 tikhub RPS 上限 = 10/s**（用户提供）
- **建议并发 ≤ 3,串行更稳**
- 触发限流时返回 `RetryError[HTTPStatusError]`,**与"接口本身不稳"报错一样,容易误判**
- App V1 限流后冷却时间长；**Web V1 抗限流更强**,App V1 被限时优先切 Web V1（同样是 V1,不是 V2）

---

## v0.2.3 — 2026-04-21


3 处迭代 — 都来自实战暴露的盲区。

- **crack 输出升级为 4 维钩子拆解**（视觉 / 文字 / 口播 / 剧情 + 综合权重）。原"4 行钩子句"把"钩子"窄化成了一句标题，丢掉了视觉/口播/剧情层 — 仿写时只能抄文案，抄不到开场设计。综合权重告诉你哪一维是主驱动力，决定仿写精力分配。
- **关键词单一中文词**（铁律）：search V1/V2 接口对带空格组合不稳定，Step 2 矩阵词改为 2-4 字单一词，多词分次搜。原 SOP 推荐空格组合词（"AI 萌宠 + 传统手工艺"），实测易失败。
- **multimodal 退化策略**（铁律 #7 补丁）：当 `fetch_note_image` / `analyze_image` 不可用时，用 `feed_notes_v2.video_info_v2.media.video.bbox.ocr_v2/v3` 字段（含封面文字位置）+ desc + 标签推断封面公式 — 但必须明文标 ⚪ 推断 / 🟢 高可信。
- **三平台手册新增 §0.5 算法规则速查**（T0/T1 可执行版）：每平台 7 条核心规则，每条带「怎么做（动作）」+「不做的代价」，诊断时第一屏可见。把分散在阈值表 / 行动清单 / 关键铁律里的"必做项"提到顶部。
- **平台算法核心信号差异化标注 + 新增视频号手册**：诊断不再"面面俱到平均用力"，每个平台明文标⭐ **算法命门**（差距 ≥ 1 档优先于其他维度修）：
  - 抖音 = **完播率**（5s → 全程）
  - 小红书 = **互动率**（CES：评 / 转 / 关高权重）
  - 快手 = **跳出 / 留存 + 关注转化**（老铁经济）
  - 视频号 = **分享率**（社交关系链分发，新增 `platforms/wechat-channels.md`）
  - `diagnostic-mode.md §4` 表格新增"⭐ 算法核心信号（命门）"列；SKILL.md description 增加"视频号"。

---

## v0.2.0 — 2026-04-21 — 重构为生产工具

**核心定位转变**：从"诊断报告生成器"重构为**生产闭环工具**。
不再默认跑 6 维评分诊断，而是直接对着具体爆款 → 输出**可发的下一条笔记初稿**。

### 新增（L1 主流程 — 三命令闭环）

- **`find`**：5 步铁律找真对标
  1. 多模态识别我的"内容本质"（5 个抽象维度）
  2. 维度交叉 → 4-6 个搜索词矩阵（**禁止单关键词搜**）
  3. 矩阵词并行 search → 候选池
  4. 候选池每条多模态过相似度（≥ 3 维相似才留）
  5. 体量 + 活跃度过滤 → 5-10 真对标 → 人工勾选
- **`crack`**：每条爆款只吐 4 行可抄元素（钩子 / 骨架 / 封面 / 标签）— 不写诊断报告
- **`adapt`**：直接给 3 标题 + 3 封面大字 + 1 首段 + 1 CTA — 可发

### 重构

- 主入口 `SKILL.md` 从 33k 字 → 10k 字（聚焦三命令 SOP）
- 旧 6 维评分 / 三层诊断 / 报告模板 → 降级到 `references/diagnostic-mode.md`（按需调用，不主推）
- §5 评分术语 → 抽出到 `references/scoring-vocab.md`（被三命令共享）
- `platforms/*.md` → 移到 `references/platforms/`（被 L2 诊断调用）

### 输出

- `./reports/` 落每次闭环产物（find / crack / adapt 各一份）
- `./assets/hooks-{platform}.md` 自动累积副产品（用户长期资产）

### 关键铁律变更

- ❌ 不再默认跑 6 维评分（用户不主动叫"为什么不爆"就不跑）
- ✅ multimodal 不省 — find Step 1 + Step 4 都必须调
- ✅ adapt 必须命中 scoring-vocab.md 公式 + 标注"抄了什么 + 改了什么"

---

## v0.1.1 — 2026-04-21

- SKILL.md §7：诊断报告必须同时落盘到 `./reports/`
- README：补 smoke test + 输出位置说明

## v0.1.0 — 2026-04-21

- 首发：三平台账号 / 内容诊断 skill
- 三层诊断框架：漏斗自检 / 对标扫描 / 六维拆解
- 多模态拆解（封面 / 视频 / 截图 OCR）
- tikhub MCP 数据底座
