---
name: social-account-doctor
description: 小红书 / 抖音 / 快手 / 视频号 自媒体「找对标 → 拆爆款 → 套自己」三命令闭环。给我的账号或选题方向，吐出"可发的下一条笔记初稿"。当用户说"找对标"、"拆这条爆款"、"对着这条仿写"、"下一条该写什么"、"我这个号缺爆款选题"、"帮我写一条对标 XX 的笔记"时调用。诊断模式（"为什么不爆"）走 references/diagnostic-mode.md。
---

# social-account-doctor — 找对标 / 拆爆款 / 套自己

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
[每条 4 维钩子拆解（视觉/文字/口播/剧情）+ 综合权重 + 骨架 + 封面 + 标签]
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

5 个本质维度交叉组合 → **4-6 个搜索词**：

```
维度1：「AI萌宠」  / 「拟人猫」  / 「萌宠成精」
维度2：「乡村美食」/ 「老家味道」/ 「童年回忆」
维度3：「治愈」    / 「烟火气」
维度4：「教程」    / 「手作」
维度5：「反差萌」  / 「猫师傅」
```

⚠️ **铁律**：搜索词 = **单一 2-4 字本质维度词**。
- 不要用宽泛选题词（"东北大酱"会搜出真人假对标）
- 不要带空格组合（"猫师傅 美食" 在 V1/V2 接口会 HTTPStatusError，要拆成 4-6 个单词分次搜）

#### Step 3 矩阵词并行搜索

每个矩阵词调一次 search → 按互动量倒序取 top 10 → 汇总到候选池（20-50 条，去重）。

工具：
- 小红书 `xiaohongshu_app_search_notes`（App V1, **首选**，见 §9.1）
- 抖音 `douyin_app_v3_fetch_video_search_result_v2`
- 快手 `kuaishou_app_search_video_v2`
- 视频号 `wechat_channels_fetch_search_ordinary`（综合）+ `wechat_channels_fetch_search_latest`（最新）双源对比 — 见 §9.2

**接口失败兜底**：连续 3 次 retry 失败 → 不再硬刚，让用户手甩 3-5 个对标链接 → 直接 `app_get_note_info`（小红书）/ `fetch_video_detail`（视频号）→ 跳到 crack。

**视频号特殊铁律**：视频号客户端**不输出可复制的链接 / 视频 ID**（分享出去是卡片）。**唯一入口是账号名/关键词搜索 → 锁定本号视频 → 拿 id**。不要让用户提供"视频号链接"，他给不出。

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
对每条吐 **4 维钩子拆解 + 3 行结构元素**（不写诊断报告，不打分，只罗列**可抄元素**）：

```
对标：@xxx 的「东北橘猫做大酱」(50w 赞 / 1.2k 评 / 30s)

钩子（4 维拆解）：
├ 视觉钩：拟人猫脸大特写 + 田间背景，0.5s 内出"猫看着你"的目光
├ 文字钩：封面中部一行字（OCR bbox 366,604,546x71）+ 标题「人！」感叹号
├ 口播钩：「人！其实快乐很简单，跟me下乡吧！」— 拟人猫"对人喊话"的反差
├ 剧情钩：第一秒就破壁（猫张嘴说"人！"）— 把"猫"和"观众"的层级倒过来
└ 综合：视觉 ×0.4 + 口播 ×0.6 = 治愈系反差钩  ← 主驱动力

骨架：原料展示 → 工艺过程 → 成品 → 情绪升华（4 段，命中骨架 A 场景+冲突+解决）
封面公式：D 实物展示 + 暖色高对比 + 主体居中（无大字）  [🟢 跑了 multimodal / ⚪ 推断]
标签组合：#AI萌宠 #东北美食 #怀旧 #反差萌（4-5 个）
复用提示：[一句话 — 这条最值得抄的一个具体动作]
```

**为什么 4 维**：钩子不是"那一句标题"，而是视觉+文字+口播+剧情的整体开场设计。综合权重决定仿写时的精力分配方向（哪一维占比 ≥ 0.5 = 死磕那一维）。

### 钩子积累（可选，必须问 — 不要自动存）

crack 跑完所有对标后，把**完整 4 维钩子单元**（不是单句）汇总打给用户看，主动问：

```
本次 crack 提取了 N 条 4 维钩子单元：
  1. @xxx「跟me下乡」(9k 赞, 治愈系反差钩, 主驱动力=口播 0.6)
  2. @yyy「比熊求职」(13k 赞, 共鸣型反差钩, 主驱动力=文字 0.7)
  ...

要积累到 ./assets/hooks-{platform}.md 吗？
  - yes：4 维拆解格式全存
  - "1,3"：只存指定条
  - no：本次不存（默认）
```

**只有用户明确说要存**，才 `mkdir -p ./assets` + 追加（按**情绪锚点**分类，再按**主驱动力**二级索引；追加不覆盖；首次创建时建好"索引 + 速查"骨架）。
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

### 5.1 PDF 输出（按需，不默认）

**铁律**：默认只输出 `.md`，**不要主动生成 PDF**。只有用户**明确说**「整理成 PDF / 出 PDF / 出一份 pdf 版」等才跑：

```bash
python3 ~/.claude/skills/social-account-doctor/scripts/render_report_pdf.py \
  ./reports/{report}.md
# 输出 ./reports/{report}.pdf （同名同位）
```

脚本特性：
- A4 + 思源黑体 (CJK 必装 Source Han Sans SC) + 粉色诊断主题
- md 中本地图片 `![](path)` 自动 base64 内嵌（PDF 自包含，可单文件传播）
- 富排版（卡片式 top N 对标 / TL;DR 红框 / 三图横排）需在 md 里**直接写 inline HTML**，CSS 已经准备好对应 class：
  - `<div class="tldr"><div class="verdict">...</div>...</div>` — TL;DR 高亮框
  - `<div class="card"><div class="card-img"><img/></div><div class="card-body">...</div></div>` — 对标卡片
  - `<div class="user-img"><img/><div class="caption">...</div></div>` — 三图横排
- 想保留中间 HTML 自己改样式：加 `--keep-html`

**何时主动询问 PDF**：用户说「分享给客户」「打印」「存档」「发出去」等需要可携带版本的语义时，可以**主动问一句**「要不要顺便出一份 PDF？」 — 不要不问就出。

---

## 6. L2 诊断模式（按需，不主推）

只在用户**明确说**这些话时触发 → 调 `references/diagnostic-mode.md`：

- "这条为什么不爆"
- "完整诊断"
- "我这个号该往哪调"
- "卡在哪一层"

→ 走 6 维评分 + 三层诊断 + 平台阈值表（完整流程，被降级为兜底）。

**否则不要主动跑诊断。** 生产闭环是 find→crack→adapt，诊断是数据回收后的**事后**反思工具。

---

## 7. 工具速查

### tikhub CLI（按平台 × 任务）

> 调用走 `tikhub <platform> <tool> --args`（CLI 自包含在仓库 `tikhub/` 目录，纯 Python stdlib + HTTP JSON-RPC + session 缓存）。不知道工具名时 `tikhub list <platform> <关键词>` 模糊查；看完整 schema 用 `tikhub describe <platform> <tool>`。

**参数类型铁律（防"看着对其实数据被破坏"）**：
- CLI 默认所有 `--key=value` **按 string 透传**，只 `true/false/null/none` 字面量被 coerce
- ID 字段（`user_id` / `photo_id` / `note_id` / `sec_user_id` / `aweme_id`）几乎都是 string schema — **直接 `--user_id 4253294011`**，不要包 `:int`
- 真要 int 用显式 tag：`--page:int=1` / `--count:int=20`；复杂结构用 `--json '{...}'`
- 看到 `validation error ... input_type=int` → 检查是不是手贱加了 `:int`

| 任务 | 小红书 | 抖音 | 快手 | B 站 |
|---|---|---|---|---|
| **find Step 3 关键词搜** | `xiaohongshu_app_search_notes`（App V1, 见 §9.1） | `douyin_app_v3_fetch_video_search_result_v2` | `kuaishou_app_search_video_v2` | `bilibili_web_fetch_general_search` |
| **find Step 5 账号信息** | `xiaohongshu_app_get_user_info`（App V1, 见 §9.1） | `douyin_web_handler_user_profile` | `kuaishou_app_fetch_one_user_v2` | `bilibili_web_fetch_user_profile` + `_user_up_stat` + `_user_relation_stat` |
| **find Step 5 用户作品列表** | `xiaohongshu_app_get_user_notes`（App V1） | `douyin_web_fetch_user_post_videos` | `kuaishou_app_fetch_user_post_v2` | `bilibili_web_fetch_user_post_videos` |
| **crack 笔记/视频详情（最稳兜底）** | `xiaohongshu_app_get_note_info`（App V1, 需 `xsec_token`） | `douyin_app_v3_fetch_one_video` | `kuaishou_app_fetch_one_video` | `bilibili_web_fetch_one_video` |
| **crack 拿封面/视频** | 用 `app_get_note_info` 返回里的 `image_list` / `video` URL（无独立接口, 见 §9.1） | `douyin_app_v3_fetch_video_high_quality_play_url` | `kuaishou_app_fetch_one_video`（含 play_url） | `bilibili_web_fetch_video_subtitle`（字幕拆口播） |
| **crack 拿评论** | `xiaohongshu_app_get_note_comments`（App V1） | `douyin_app_v3_fetch_video_comments` | `kuaishou_app_fetch_one_video_comment` | `bilibili_web_fetch_video_comments` + `_comment_reply` |
| **B 站独家：弹幕** | — | — | — | `bilibili_web_fetch_video_danmaku`（4 类信号见 platforms/bilibili.md §3） |
| **解析分享链接** | `xiaohongshu_web_get_note_id_and_xsec_token` | `douyin_app_v3_fetch_one_video_by_share_url` | `kuaishou_web_fetch_one_video_by_url` | `bilibili_web_bv_to_aid`（bv ↔ aid 转换） |

### 视频号（独立路径 — 没分享链接）

视频号客户端**不输出可复制的链接 / 视频 ID**（分享出去是卡片，不是 URL）。所以任何视频号任务的入口都是**账号名/关键词搜索**，跟其他三平台流程不一样：

| 任务 | 工具 | 注意 |
|---|---|---|
| **find Step 3 关键词搜（综合）** | `wechat_channels_fetch_search_ordinary` | 算法综合排序，含权重 + 关系链 |
| **find Step 3 关键词搜（最新）** | `wechat_channels_fetch_search_latest` | 时间序，与综合求差集找蓝海窗口 |
| **find Step 5 账号搜索** | `wechat_channels_fetch_user_search` | ⚠️ 实测易 503 — fallback：用 `_search_ordinary` 精确匹配 nickname |
| **crack 视频详情** | `wechat_channels_fetch_video_detail`（`id` 优先于 `exportId`） | 含完整互动数据 + `feed_count`（账号总作品数） |
| **crack 拿评论** | `wechat_channels_fetch_comments` | — |
| **账号主页 / 直播回放** | `wechat_channels_fetch_home_page` / `wechat_channels_fetch_live_history` | — |
| **热榜 / 抢窗口** | `wechat_channels_fetch_hot_words` | 视频号专属：朋友圈关系链 + 热榜双驱动 |

**视频号 find 的 5 步要做两个调整**：
1. Step 3 关键词搜要**双源跑**（ordinary + latest），交集 = 已被算法验证的爆款，差集 = 新发未推 / 老爆款长尾
2. Step 5 账号信息时，user_search 503 是常态 — fallback 是从 `search_ordinary` 结果里按 nickname 精确匹配 + 头像 url 校验

### B 站（横版 + 三连 + 弹幕，跟其他四平台都不同）

B 站是 16:9 横屏 + 长视频文化，**算法核心信号是三连率（点赞 + 投币 + 收藏 / 播放）**，不是完播率，也不是收藏比。**弹幕**是其他平台都没有的实时情绪流，每条对标必跑：

| 任务 | 工具 | 注意 |
|---|---|---|
| **关键词搜（综合 / 时间窗口）** | `bilibili_web_fetch_general_search` | `order` 用 `totalrank`/`click`/`pubdate`/`stow`(收藏) 等；蓝海词监控用 `pubtime_begin_s` |
| **视频详情** | `bilibili_web_fetch_one_video` | 含 `cid`（拉弹幕用）+ stat 全字段（投币 / 收藏 / 弹幕） |
| **弹幕（独家信号）** | `bilibili_web_fetch_video_danmaku --cid <cid>` | 4 类信号：梗 / 问题 / 打卡 / 吐槽 — 详见 platforms/bilibili.md §3 |
| **字幕（拆口播结构）** | `bilibili_web_fetch_video_subtitle --aid --cid` | AI 字幕（如有） |
| **UP 主（双统计）** | `bilibili_web_fetch_user_profile` + `_user_up_stat` + `_user_relation_stat` | 三个分别拿基本信息 / 总播放点赞 / 粉丝关注 |
| **UP 主投稿 + 动态** | `bilibili_web_fetch_user_post_videos` + `_user_dynamic` | 动态看是否在 B 站外引流 / 预告 |
| **bv ↔ aid 转换** | `bilibili_web_bv_to_aid` | URL 输入支持用 `bilibili_web_fetch_one_video_v3` |

**B 站 find 关键差异**：
1. **按三连率排序而不是播放量**：拉到结果后算 `(coin + favorite + like) / view`，按这个排
2. **每条对标必拉弹幕**：弹幕里的"打卡时间戳"直接告诉你哪一段是高潮（剪短视频投抖音/小红书复用素材）
3. **看 UP 主 = 看分区垂直度**：分区跨度 ≥ 3 个的 UP 主算法不推

详见 `references/platforms/bilibili.md`。

平台细节（阈值、6 维评分细则）在 `references/platforms/{平台}.md`，**find/crack/adapt 主流程不用看**，L2 诊断时才读。

### 多模态脚本（scripts/）
- `analyze_image.py <封面>`：拿 5 变量 + 5 模板归类 + 钩子识别
- `analyze_video.py <视频> [--mode auto/talking/visual/keyframe]`：三模式自动路由
- `ocr_screenshot.py <截图>`：用户给后台数据截图时用
- `dispatch_account.py <账号URL>`：链接 → platform + user_id
- `render_report_pdf.py <md> [-o out.pdf] [--keep-html]`：md 报告 → PDF（**按需，不默认**，详见 §5.1）

---

## 9. 接口稳定性表（按平台分小节）

### 9.1 小红书（**复测 2026-04-22 — App V1 全套是首选, App V2 仍全挂, Web V2 部分挂 + 官方明确停止维护**）

> ⚠️ **新结论**: 全面切换到 **App V1**。之前我们把 Web V2 当详情/评论/封面的兜底, 但 (1) tikhub 官方明确说 Web V2 已停止维护, 随时可能下线; (2) `web_v2_fetch_note_image` 实测已挂; (3) **App V1 全套都活着** (search / note_info / comments / user_info / user_notes), 不用绕远路。
>
> **官方说法 vs 实测**：
> - 官方 (2026-04 用户透露): "小红书 App V2 系列是最新最稳定版本; Web V2 和 Web 系列已停止维护"
> - 实测 (2026-04-22): App V2 全部 RetryError; Web V2 部分能用部分挂; **App V1 反而最稳**
> - **以实测为准** — 哪天 App V2 真恢复了, 复测后再切。
>
> **官方明确弃用** (tikhub list 里也直接打了 `[已弃用/Deprecated]` 标签, 我们已经没在用):
> - `xiaohongshu_app_search_notes_v2` (注意命名: `app_search_notes_v2` ≠ `app_v2_search_notes`)
> - `xiaohongshu_app_get_video_note_info`
> - `xiaohongshu_app_get_notes_by_topic`
> - `xiaohongshu_app_search_users` (App V1 这个挂了, 改用 Web V1 的 `web_search_users`)
> - 见到这些**永远不要用**

| 任务 | ✅ 首选 (App V1, 实测 200) | ⚠️ 备选 (实测能跑但有风险) | ❌ 不要用 |
|---|---|---|---|
| **关键词搜笔记** | `xiaohongshu_app_search_notes` | `xiaohongshu_web_search_notes` (Web V1, 限流时切这个) | `app_v2_search_notes` (实测挂) / `web_v2_fetch_search_notes` (实测挂) / `app_search_notes_v2` (官方弃用) |
| **关键词搜用户** | — (App V1 这个挂了) | `xiaohongshu_web_search_users` (Web V1, **唯一能用**) | `app_search_users` (官方弃用) / `app_v2_search_users` / `web_v2_fetch_search_users` |
| **笔记详情** | `xiaohongshu_app_get_note_info` (需 `xsec_token`, 从 search 结果或 share link 解析里拿) | `xiaohongshu_web_v2_fetch_feed_notes_v2` (实测能用但**官方说停维护, 别长期依赖**) / `xiaohongshu_web_get_note_info_v7` (Web V1, 实测 200) | `app_v2_get_image_note_detail` / `_get_video_note_detail` (实测挂) |
| **笔记评论** | `xiaohongshu_app_get_note_comments` | `xiaohongshu_web_v2_fetch_note_comments` (官方说停维护) | `app_v2_get_note_comments` (实测挂) |
| **二级评论** | `xiaohongshu_app_get_sub_comments` | `xiaohongshu_web_v2_fetch_sub_comments` (官方说停维护) | `app_v2_get_note_sub_comments` (实测挂) |
| **账号信息** | `xiaohongshu_app_get_user_info` ✨ (**之前以为没接口, 实测可用**) | — (Web V2 的 `fetch_user_info` 系列官方说停维护) | `app_v2_get_user_info` / `web_get_user_info_v2` (实测挂) |
| **用户作品列表** | `xiaohongshu_app_get_user_notes` | `xiaohongshu_web_v2_fetch_home_notes` (官方说停维护) | `app_v2_get_user_posted_notes` (实测挂) |
| **拿封面/图片** | 用 `app_get_note_info` / `web_get_note_info_v7` 返回里的 `image_list` URL (**没有独立的 image 接口能用**) | — | `web_v2_fetch_note_image` (实测挂) |
| **分享链接解析** | `xiaohongshu_web_get_note_id_and_xsec_token` (用户给的 xhslink 短链 → note_id + xsec_token) | `xiaohongshu_app_extract_share_info` / `app_get_user_id_and_xsec_token` | — |

**铁律**：
- ✅ **首选 App V1 全套** — search / note_info / comments / user_info / user_notes 都活, 不要绕去 Web V2
- ⚠️ **Web V2 接口**实测能用但**官方明确说停止维护**, 只在 App V1 也挂 + 实在没办法时用, 写报告时标 ⚠️ "Web V2 备用, 官方已停维护, 数据可能延迟或随时下线"
- ❌ **App V2 全系列**实测全挂, 不要再去试; 官方说稳定但我们以实测为准
- ❌ 同一接口连续 3 次 HTTPStatusError → 按上表换备选 / 让用户截图代替
- ❌ **小红书不支持按话题标签 (hashtag) 搜笔记**, 只支持关键词 (tikhub 官方确认 2026-04) — 用户问"搜 #XX 标签下的爆款"时, 告诉他"只能搜关键词, 标签搜索小红书没开放"
- ✅ 没列在表里的功能 (粉丝/关注列表、合集), 当前 tikhub 接口可能全挂, **优先让用户截图代替**
- 📅 实测日期写在标题里, 3 个月后必须重测一次; tikhub 哪天通知 Web V2 下线 → 立刻清掉"备选"列

**xsec_token 怎么拿** (App V1 笔记详情/评论需要这个 token):
- search 结果每条 note 里都带 `xsec_token` 字段, 直接抄
- 用户给的 xhslink 短链 → 调 `xiaohongshu_web_get_note_id_and_xsec_token --share_link <url>` 解析
- 用户给的完整笔记 URL `xiaohongshu.com/explore/<note_id>?xsec_token=XXX` → URL 参数里直接读

**并发与限流（实测 2026-04-21）**：
- **当前 tikhub RPS 上限 = 10/s**（用户提供）—— 单次诊断的搜索批量调用要节制,**建议并发不超过 3,串行更稳**
- 触发限流时返回 `RetryError[HTTPStatusError]`（与"接口本身不稳"的报错一样,容易误判）
- App V1 (`xiaohongshu_app_search_notes`) 限流后冷却时间长；**Web V1 (`xiaohongshu_web_search_notes`) 抗限流更强**,App V1 被限时优先切 Web V1（同样是 V1，不是 V2）

### 9.2 视频号（实测 2026-04-21）

| 任务 | ✅ 用这个 | ⚠️ 注意 |
|---|---|---|
| 关键词综合搜索 | `wechat_channels_fetch_search_ordinary` | 稳。结果里的 `source.title` 可能是带 `<em class="highlight">` 的高亮 HTML，处理时要剥标签 |
| 关键词最新搜索 | `wechat_channels_fetch_search_latest` | 偶发 503，retry 1 次即可 |
| 账号搜索 | `wechat_channels_fetch_user_search` | **实测高频 503**。fallback：用 `_search_ordinary(账号名)` 取首条 + 校验 nickname/头像 url |
| 视频详情 | `wechat_channels_fetch_video_detail` | 稳。**优先传 `id`** 而非 `exportId`；返回的 `contact.feed_count` 是账号总作品数（冷启诊断关键字段） |
| 评论列表 | `wechat_channels_fetch_comments` | 稳 |
| 用户主页 | `wechat_channels_fetch_home_page` | 依赖 user_search 提供 user 上下文，user_search 挂时连带挂 |
| 热门话题 | `wechat_channels_fetch_hot_words` | 稳 |

**视频号铁律**：
- ❌ **不要让用户提供视频号链接 / 视频 ID** — 视频号客户端只支持卡片分享，根本不输出 URL/ID
- ❌ user_search 503 时**不要 retry 超过 1 次** — 直接 fallback 到 `_search_ordinary` + nickname 精确匹配
- ✅ 综合搜索结果里**真号常常只有 1 条**（同名/同主题号会被高亮但来自其他号），按 `source.title` 剥 `<em>` 后 **完全等于** 目标账号名才算真号
- ✅ `video_detail.contact.feed_count == 1` + `like/comment/forward 全 0` = **冷启失败号**，可直接出诊断结论
- 📅 实测日期写在标题里，3 个月后重测

### 9.3 抖音（待实测，2026-04-21 未做接口稳定性实证）

🟡 **状态**：当前 SKILL.md §7 列的抖音工具按经验沉淀，**未在本轮（2026-04）做接口稳定性实证**。视频号实测发现"同 tikhub 平台 V2 接口存在批量崩溃模式"（小红书 V2 全挂），抖音 / 快手是否同样受影响**未知**。

**实测命令**（用 tikhub CLI）：
```bash
tikhub --health                                                    # 通连
tikhub list douyin search                                          # 看可用搜索工具
tikhub douyin douyin_app_v3_fetch_video_search_result_v2 \
  --keyword Cursor --offset 0 --count 10                           # 真实调用
```

实测后回填这张表：

| 任务 | 实测结果 | 备注 |
|---|---|---|
| `douyin_app_v3_fetch_video_search_result_v2` | 待测 | — |
| `douyin_web_handler_user_profile` | 待测 | — |
| `douyin_app_v3_fetch_one_video` | 待测 | — |
| `douyin_app_v3_fetch_video_comments` | 待测 | — |
| `douyin_app_v3_fetch_one_video_by_share_url` | 待测 | — |

**铁律（参照视频号/小红书外推，未实证）**：
- 同接口连续 3 次 RetryError → 不要硬 retry，按 `xhs/wechat-channels` 的 fallback 模式找替代版本号（v3 → v2 → web）
- 抖音 `share_url` 解析比小红书 `xsec_token` 体系稳，分享链接路径优先

### 9.4 快手（待实测，同 9.3）

🟡 **状态**：同 §9.3，未在本轮做接口稳定性实证。

**实测命令**：
```bash
tikhub --health
tikhub list kuaishou search
tikhub kuaishou kuaishou_app_search_video_v2 --keyword Cursor --page 1
```

实测后回填：

| 任务 | 实测结果 | 备注 |
|---|---|---|
| `kuaishou_app_search_video_v2` | 待测 | — |
| `kuaishou_app_fetch_one_user_v2` | 待测 | — |
| `kuaishou_app_fetch_one_video` | 待测 | — |
| `kuaishou_app_fetch_one_video_comment` | 待测 | — |
| `kuaishou_web_fetch_one_video_by_url` | 待测 | — |

---

1. **find 必须 5 步走**：本质识别 → 矩阵搜 → 多模态过滤 → 体量过滤 → 人工勾选。任何一步都不能省。
2. **不要单一宽泛词搜对标**（如"东北大酱"）。永远是 4-6 个本质维度词矩阵。
3. **search 关键词必须是单一中文词，2-4 字最稳，禁止空格组合**（带空格的组合词在 V1/V2 接口都易 HTTPStatusError — 拆成多个单词分次搜更稳）。
4. **crack 输出 4 维钩子拆解**（视觉/文字/口播/剧情 + 综合权重），不是单句钩子。综合权重决定仿写时的精力分配。
5. **adapt 必须命中 scoring-vocab.md 公式**，且必须标注"抄了什么 + 改了什么"。
6. **诊断不主推**。除非用户明确说"为什么不爆"，否则不要走 L2。
7. **multimodal 不省**：find Step 1 看我的、find Step 4 看候选 — 都要调。token 贵但不能省。
   - 退化兜底：`web_v2_fetch_note_image` 已实测挂, 用 `app_get_note_info` 返回里的 `image_list` URL 自己 curl 下载封面, 或用 `note_info` 里的 OCR / desc / 标签字段推断封面公式, **必须明文标 ⚪ 推断 / 🟢 高可信**。
8. **完整闭环跑完才落盘**，半成品只在对话里说。
9. **钩子库要问过用户才追加**。crack 完成后主动问"要存吗"，用户答 yes 才写 `assets/hooks-{platform}.md`，按 4 维拆解格式存（不是单句）。**禁止自动追加**。
10. **环境自检 + 缺失透明**（最重要的一条 — 防"伪装完成"）：

   **开干前必做**：列出本次任务依赖的工具，逐个 ping。
   - `find` 依赖：tikhub CLI（`tikhub --health`）+ analyze_image.py + analyze_video.py
   - `crack` 依赖：tikhub CLI（笔记/视频/评论详情）+ multimodal 脚本
   - `adapt` 依赖：纯 LLM（无外部依赖）
   - L2 完整诊断依赖：tikhub CLI（搜对标 + 账号信息）+ multimodal

   **缺哪个明说哪个**（在第一句话就说，不要默默缩范围）：

   ```
   ⚠️ 本次需要 tikhub CLI（小红书）调数据，环境检查发现：
      - tikhub --health 不通 / TIKHUB_API_KEY 没配 / 连续 retry 失败

   两个选择：
   ① 修复 ~/.claude/.env 的 TIKHUB_API_KEY 或 PATH（详见仓库 `tikhub/README.md`），再来一次
   ② 你直接给我 N 个对标链接 / 截图 — 我跳过搜索阶段，从 crack 开始
   ```

   **禁止偷工**：
   - 跑了 1/3 不能说"诊断完成"
   - 跑完后必须明文标注：「本次只完成 Layer X，因为 Y 工具不可用 / Y 数据缺失」
   - **半成品不写盘**（不污染 reports/ 目录）
   - 接口连续 3 次 retry 失败 → 视同工具不可用 → 进入上面的话术

11. **脚本层信任、账号资料层保守**（防"AI 自信地把账号带偏"）：

    - **脚本/内容层**（标题 / 封面大字 / 首段 / CTA / 钩子 / 骨架 / 选题 / 单条改写 / 视频脚本）→ 按 find / crack / adapt 流程**直接吐**，不必反复"建议确认"。错了下条改回来成本低。
    - **账号资料层**（账号定位重写 / 简介改写 / 人设调整 / 赛道切换 / 粉丝画像判定 / 变现模式建议）→ **保守输出，缺数据宁可不说也不编**：
      - 缺数据时直接写「数据不足，暂不下结论」，**不要凭"行业经验"补一个定位**
      - 给修改建议**必须标注依据**（哪条数据 / 哪个对标 / 哪条评论证明），没依据就不写
      - 多给"试一下看反馈"的方向，少给"必须改成 X"的断言
      - 任何「建议把简介改成 X」/「你应该重新定位为 Y」**先在对话里问用户**「我手里只有 Z 数据，这条结论你觉得靠谱吗」再写盘
      - 接口失败 / 数据缺失时，账号资料相关诊断**直接跳过**，不要"基于经验推断"凑数

    **Why**：内容层错了下条改回来成本低；账号资料一改影响所有未来推荐 + 标签，反复横跳会污染账号权重。看似自信但其实是 AI 推断的"账号建议"会把整个号带偏。

12. **tikhub 调用走 CLI，不走 `claude mcp add`**：所有 tikhub 数据抓取通过 `tikhub <platform> <tool> --args` CLI 命令调用。**CLI 自包含在仓库 `tikhub/` 目录**（不依赖外部 skill）。**不要再 `claude mcp add tikhub-*`**：

    - HTTP 端点是 `https://mcp.tikhub.io/{xiaohongshu|douyin|kuaishou|wechat|bilibili}/mcp`，所有平台共用一个 CLI、一个 API key
    - 不需要重启 claude，不污染全局工具列表
    - session id 自动缓存（5 min TTL），不用关心连接管理

    **环境自检**：
    ```bash
    tikhub --health                              # {"status":"healthy",...} → OK
    tikhub list xiaohongshu search               # 工具目录可读
    ls ~/.claude/.env                            # API key 存这里（chmod 600）
    ```

    新机器初始化（`git clone` 之后一次性）：
    ```bash
    cd ~/.claude/skills/social-account-doctor
    ln -sf "$(pwd)/tikhub/bin/tikhub" ~/.local/bin/tikhub   # 让 tikhub 命令在 PATH
    echo "TIKHUB_API_KEY=YOUR_KEY" >> ~/.claude/.env
    chmod 600 ~/.claude/.env
    ```
    详见 `tikhub/README.md`。

---

## 9. 数据时效性说明

`references/platforms/*.md` 里所有平台阈值（完播率 / CTR / CES 等）均为**行业经验值**（蝉妈妈 / 千瓜 / 新红 / COO 公开发言等多源），**非平台官方公告**。

📅 **采集日期：2026-04**｜**建议复核：每 6 个月**

诊断时用作"方向判断"，**不是"绝对死线"**。生产闭环（find/crack/adapt）不依赖这些数字。
