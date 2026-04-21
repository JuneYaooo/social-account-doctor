---
name: account-diagnostic
description: 小红书 / 抖音 / 快手 自媒体「找对标 → 拆爆款 → 套自己」三命令闭环。给我的账号或选题方向，吐出"可发的下一条笔记初稿"。当用户说"找对标"、"拆这条爆款"、"对着这条仿写"、"下一条该写什么"、"我这个号缺爆款选题"、"帮我写一条对标 XX 的笔记"时调用。诊断模式（"为什么不爆"）走 references/diagnostic-mode.md。
---

# account-diagnostic — 找对标 / 拆爆款 / 套自己

> **不挖钩子建仓库，不写诊断报告。**
> 直接对着具体爆款 → 输出**我的下一条笔记初稿**（标题 + 封面大字 + 首段 + CTA）。

---

## 0. 闭环图

```
[我的账号 / 选题方向]
       │
       ▼ ① find  (多模态识别本质 → 矩阵搜 → 相似度过滤)
[5-10 个真对标爆款]
       │
       ▼ 人工勾选 3-5 条 ✋
[选定对标]
       │
       ▼ ② crack
[每条 4 行：钩子句 / 三段骨架 / 封面公式 / 标签组合]
       │
       ▼ ③ adapt
[3 标题 + 3 封面大字 + 1 段首段 + 1 个 CTA]  → 可发
```

**副产品（可选，必须问）**：crack 跑完后**主动问**用户「要把这些钩子积累到 `./assets/hooks-{platform}.md` 吗？」 — 用户答 yes 才追加。**不会自动写**。库的质量由你把关，跑多了自然形成弹药库。

---

## 1. 输入路由

| 用户说什么 | 走哪个命令 |
|---|---|
| "找对标" / "我这个号有什么对标" / "扫一下同赛道" | **find** |
| "拆这条爆款" / "这条为什么爆" / "提取这条的钩子" | **crack**（单条） |
| "对着这条仿写" / "下一条该怎么写" / "套这条的钩子写一条" | **crack + adapt** |
| "我想发 XX 主题，有什么参考" / "缺爆款选题" | **find + crack + adapt**（全闭环） |
| "为什么我这条不爆" / "完整诊断" / "这个号该往哪调" | → `references/diagnostic-mode.md`（L2 兜底，不主推） |

---

## 2. find 命令 SOP（5 步铁律）

### 输入
我的账号链接 / 我的某条笔记链接 / 一个选题方向（"我想发 XX"）

### 输出
5-10 个对标爆款链接 — **不是关键词搜出来的，是按内容本质过滤过的**。

### 5 步（每一步都不能省）

#### Step 1 内容本质识别（必跑多模态）

输入是我的账号 / 笔记 → 调 `analyze_image.py`（封面）+ `analyze_video.py`（视频）→ 提取 **5 个本质维度**：

| 维度 | 例子（橘猫做大酱那条） |
|---|---|
| 载体形态 | AI 拟人化小动物（不是真人 / 真宠物） |
| 情绪锚点 | 怀旧 / 家乡味道 / 童年记忆 |
| 审美风格 | 暖阳 + 慢镜头 + 烟火气 |
| 内容结构 | 教程类（原料 → 成品全流程） |
| **反差点** | **可爱角色 × 硬核农活**（核心爆点） |

**输出**：5 个维度的描述（每个 1 句话）+ 形容词三元组（如：AI 萌宠 / 怀旧 / 反差教程）。

#### Step 2 生成搜索词矩阵

5 个本质维度交叉组合 → **4-6 个搜索词组合短语**：

```
维度1 + 维度4：「AI 萌宠 + 传统手工艺」
维度1 + 维度2：「拟人动物 + 老家美食」
维度4 + 维度5：「动画角色 + 慢节奏教程」
维度3 + 维度5：「治愈系 + 反差萌教程」
```

⚠️ **铁律**：**禁止用单一关键词**（如"东北大酱"）— 会搜出真人主播假对标。一定是组合。

#### Step 3 矩阵词并行搜索

每个矩阵词调一次 search → 按互动量倒序取 top 10 → 汇总到候选池（20-50 条，去重）。

工具：
- 小红书 `xiaohongshu_app_v2_search_notes`
- 抖音 `douyin_app_v3_fetch_video_search_result_v2`
- 快手 `kuaishou_app_search_video_v2`

#### Step 4 多模态相似度过滤（必跑多模态）

候选池每条抽首图 → `analyze_image.py` → 按 5 维打分（0-1）→ **≥ 3 维相似才留**。

⚠️ **代价警告**：这一步 20-50 次 multimodal 调用，**token 不便宜，但不能省** — 否则 find 出来的全是表面假对标，后面 crack/adapt 全白做。

#### Step 5 体量 + 活跃度过滤

| 条件 | 标准 |
|---|---|
| 粉丝量 | 我 ×1 ~ ×10（伙伴/榜样档，删大佬级和小白级） |
| 近 30 天发文 | ≥ 8 条（不活跃删） |
| 单条互动 | ≥ 该号近 30 天均值 × 3（爆款不是日常） |
| 排除 | 官方蓝 V / 单条 100w+ 异常爆（不可复制） |

→ **输出 5-10 个真对标 + 每个贴一句"为什么是真对标"**（5 维相似度命中哪几维）。

### find 的人工卡点

最后一步**必须**给用户看清单 → 用户勾选 3-5 条 → 没勾的不进 crack。

---

## 3. crack 命令 SOP

### 输入
1 个或 N 个对标爆款链接（一般是 find 勾选出来的）。

### 输出
对每条**只**吐 4 行（不写诊断报告，不打分，只罗列**可抄元素**）：

```
对标：@xxx 的「东北橘猫做大酱」(50w 赞)

钩子句：「今天咱做东北老酱块子」+ AI 拟人萌宠首帧抓眼
骨架：原料展示 → 工艺过程 → 成品 → 情绪升华（4 段，命中骨架 A 场景+冲突+解决）
封面公式：D 实物展示 + 暖色高对比 + 主体居中（无大字）
标签组合：#AI萌宠 #东北美食 #怀旧 #反差萌（4-5 个）
```

### 钩子积累（可选，必须问 — 不要自动存）

crack 跑完所有对标后，把钩子句汇总打给用户看，主动问：

```
本次 crack 提取了 N 条钩子句：
  1. 「今天咱做东北老酱块子」(@xxx, 50w 赞, 反差萌)
  2. 「我的老家就住在这个屯」(@xxx, 32w 赞, 怀旧)
  ...

要积累到 ./assets/hooks-{platform}.md 吗？
  - yes：全部追加
  - no：本次不存（默认）
  - "1,3"：只存指定条
```

**只有用户明确说要存**，才 `mkdir -p ./assets` + 追加（按情绪锚点 / 反差点分类，追加不覆盖）。
**不要默认存** — 自动堆出来的钩子库都是垃圾，库的价值在于人工把关。

### crack 用到的术语
封面 ABCDE / 标题 1-10 / 骨架 ABC / 钩子 1-7 → 全部对齐 `references/scoring-vocab.md`。

---

## 4. adapt 命令 SOP

### 输入
- 我的账号定位（一句话，必须）
- crack 输出（1-N 个对标的元素清单，必须）
- 我想发的方向（可选，没有就基于 crack 推荐）

### 输出
**直接给可发的**：

```
标题候选（3 个，每个标注命中哪个公式）：
  1. 「[文案]」 — 公式 4 怕错避坑 + 改了 XX
  2. 「[文案]」 — 公式 2 反认知 + 改了 XX
  3. 「[文案]」 — 公式 6 身份共鸣 + 改了 XX

封面大字（3 个，4 字以内）：
  1. 「[大字]」 — 套对标的 D 模板，加大字升级到 A+D 混合
  2. ...
  3. ...

首段文案（≤ 50 字，命中钩子模板 N 号）：
  「[文案]」 — 抄了对标的 XX，我做了 YY 改动

CTA（命中互动钩子模板）：
  「[文案]」 — 套对标的"评论扣 X 送 Y"结构
```

### adapt 的铁律
- 标题 / 封面 / 首段 / CTA **必须命中** `references/scoring-vocab.md` 里的至少 1 个公式
- 每个产出**必须标注**「抄了对标什么 + 我做了什么改动」 — 防止抄到不可复制的部分
- 不要 4 个候选，**就 3 个**（多了用户选不动）

---

## 5. 输出位置铁律

完整闭环（find → crack → adapt）跑完，**必须**落盘到当前工作目录：

```
./reports/
  {YYYYMMDD-HHMM}-find-{我的账号末8位}.md      # 5-10 对标 + 为什么是真对标
  {YYYYMMDD-HHMM}-crack-{对标末8位}.md         # 每条 4 行清单
  {YYYYMMDD-HHMM}-adapt-{选题短码}.md          # 标题 + 封面 + 首段 + CTA

./assets/                                     # 副产品，跨任务累积
  hooks-xhs.md / hooks-douyin.md / hooks-kuaishou.md
```

写盘前 `mkdir -p ./reports ./assets`。**只跑了 1 个命令、半成品、接口失败 → 不写盘**，只在对话里说。

---

## 6. L2 诊断模式（按需，不主推）

只在用户**明确说**这些话时触发 → 调 `references/diagnostic-mode.md`：

- "这条为什么不爆"
- "完整诊断"
- "我这个号该往哪调"
- "卡在哪一层"

→ 走 6 维评分 + 三层诊断 + 平台阈值表（旧 v0.1.x 的完整流程，被降级为兜底）。

**否则不要主动跑诊断。** 生产闭环是 find→crack→adapt，诊断是数据回收后的**事后**反思工具。

---

## 7. 工具速查

### tikhub MCP（按平台 × 任务）
| 任务 | 小红书 | 抖音 | 快手 |
|---|---|---|---|
| **find Step 3 关键词搜** | `xiaohongshu_app_v2_search_notes` | `douyin_app_v3_fetch_video_search_result_v2` | `kuaishou_app_search_video_v2` |
| **find Step 5 账号信息** | `xiaohongshu_web_v2_fetch_user_info` | `douyin_web_handler_user_profile` | `kuaishou_app_fetch_one_user_v2` |
| **crack 笔记/视频详情** | `xiaohongshu_web_v2_fetch_feed_notes_v2` | `douyin_app_v3_fetch_one_video` | `kuaishou_app_fetch_one_video` |
| **crack 拿封面/视频** | `xiaohongshu_web_v2_fetch_note_image` | `douyin_app_v3_fetch_video_high_quality_play_url` | `kuaishou_app_fetch_one_video`（含 play_url） |
| **crack 拿评论** | `xiaohongshu_web_v2_fetch_note_comments` | `douyin_app_v3_fetch_video_comments` | `kuaishou_app_fetch_one_video_comment` |
| **解析分享链接** | `xiaohongshu_web_get_note_id_and_xsec_token` | `douyin_app_v3_fetch_one_video_by_share_url` | `kuaishou_web_fetch_one_video_by_url` |

平台细节（阈值、6 维评分细则）在 `references/platforms/{平台}.md`，**find/crack/adapt 主流程不用看**，L2 诊断时才读。

### 多模态脚本（scripts/）
- `analyze_image.py <封面>`：拿 5 变量 + 5 模板归类 + 钩子识别
- `analyze_video.py <视频> [--mode auto/talking/visual/keyframe]`：三模式自动路由
- `ocr_screenshot.py <截图>`：用户给后台数据截图时用
- `dispatch_account.py <账号URL>`：链接 → platform + user_id

---

## 8. 关键铁律

1. **find 必须 5 步走**：本质识别 → 矩阵搜 → 多模态过滤 → 体量过滤 → 人工勾选。任何一步都不能省。
2. **不要单关键词搜对标**。永远是 4-6 个组合矩阵。
3. **crack 不写诊断报告**，只吐 4 行可抄元素清单。
4. **adapt 必须命中 scoring-vocab.md 公式**，且必须标注"抄了什么 + 改了什么"。
5. **诊断不主推**。除非用户明确说"为什么不爆"，否则不要走 L2。
6. **multimodal 不省**：find Step 1 看我的、find Step 4 看候选 — 都要调。token 贵但不能省。
7. **完整闭环跑完才落盘**，半成品只在对话里说。
8. **钩子库要问过用户才追加**。crack 完成后主动问"要存吗"，用户答 yes 才写 `assets/hooks-{platform}.md`。**禁止自动追加** — 自动堆出来的库都是垃圾，库价值在人工把关。

---

## 9. 数据时效性说明

`references/platforms/*.md` 里所有平台阈值（完播率 / CTR / CES 等）均为**行业经验值**（蝉妈妈 / 千瓜 / 新红 / COO 公开发言等多源），**非平台官方公告**。

📅 **采集日期：2026-04**｜**建议复核：每 6 个月**

诊断时用作"方向判断"，**不是"绝对死线"**。生产闭环（find/crack/adapt）不依赖这些数字。
