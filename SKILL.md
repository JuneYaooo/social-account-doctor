---
name: social-account-doctor
description: 小红书 / 抖音 / 快手 / 视频号 自媒体「(compose 素材打底 →) 找对标 → 拆爆款 → 套自己」四命令闭环，另支持带货账号诊断、带货视频链接拆解和证据驱动的脚本生成（commerce）。给账号 / 平台视频链接 / 本地视频 / 商品详情、SKU 与资质材料，输出账号与对标差距、内容拆解、商品事实卡、口播和分镜。当用户说"找对标"、"拆这条爆款"、"对着这条仿写"、"下一条该写什么"、"我这个号缺爆款选题"、"帮我写一条对标 XX 的笔记"、"我有素材帮我写一条能爆的"、"这份文档/这组图/这段视频能出一条爆款吗"时调用。诊断模式（"为什么不爆"）走 references/diagnostic-mode.md。带货触发词：带货账号诊断、带货视频链接、带货素材、商品详情截图、SKU 表、商品资质、带货脚本、口播、分镜、商品卡一致性 — 走 commerce 路由。商品链接不等于视频链接；本 Skill 不解析在线商品页，不提供选品、趋势监控或 GMV/佣金推断。
---

# social-account-doctor — 找对标 / 拆爆款 / 套自己

> **不挖钩子建仓库，不写诊断报告。**
> 直接对着具体爆款 → 输出**我的下一条笔记初稿**（标题 + 封面大字 + 首段 + CTA）。

---

## 0A. 交付质量硬规则（防伪装完成）

这些规则适用于 find / crack / adapt / diagnostic。违反时不要硬写报告；在对话里明说缺哪一步、为什么缺、用户可以怎么补。

**H1 — find 必须有真对标搜索**
- `find` 模式至少跑过 1 次平台搜索，并拿到真实账号或作品候选：小红书 `xiaohongshu_app_v2_search_notes` / 抖音账号搜索或视频搜索 / 快手 `kuaishou_app_search_video_v2` / 视频号 `wechat_channels_v2_fetch_search_channel_videos` / B 站 `bilibili_web_fetch_general_search`。
- 只拿了我的账号信息或作品列表就写“对标结论” = 违规。没有对标搜索，就只能标成“仅基于我方数据的初步判断”。

**H2 — 视觉判断必须先跑多模态**
- 报告里只要出现“封面模板 A/B/C/D/E”“大字比例”“真人出镜/实物展示/表格截图”“封面公式”“首帧钩子”等判断，就必须先用 `scripts/analyze_image.py` 分析本地封面/首帧。
- 我方账号诊断优先跑 top 3 + bottom 3；完整诊断最好覆盖近 7 条。对标可只跑 top 3，不能零调用。
- 报告正文必须嵌入我方/对标封面图，至少让用户能图文对照。无图的视觉诊断只能算口头评价。

**H3 — 半成品要显式标注**
- 搜索 API 挂、tikhub 不通、对标不足 3 条、截图字段不全、音频转写失败，都不能静默跳过。
- 报告开头或对话里必须标注完整度：`完整` / `部分（缺 Layer X）` / `仅 L1`。
- 对标为 0 条时写：`本次未能获取有效对标数据，以下结论仅基于账号自身数据，可能不够准确。`

**H4 — 标题干净，状态放正文**
- 用户可见 H1 不写 `(补充版)`、`(无对标)`、`(技术分析)`、`(Gemini 分析)` 这类内部状态词。
- 状态说明放在标题下方引用块或 TL;DR 上方。

**H5 — 账号定位不清晰要警告**
- 账号简介为空/模糊、近 30 条覆盖 4 个以上不相关赛道、作品数 < 10、简介和内容明显不符时，必须在报告开头提示“定位风险”。
- 涉及账号定位、简介改写、人设切换、粉丝画像、变现模式时，缺硬数据就写“数据不足，暂不下结论”，不要凭感觉改号。

**H6 — 报告语言面向非技术用户**
- 用户报告里不要出现脚本名、模型名、API 名、命令行、JSON、ffmpeg、OCR bbox 等技术实现细节。
- 写“从封面设计来看……”“在平台上搜索同赛道内容发现……”，不要写“通过 analyze_image.py / tikhub 接口 / Gemini 得出……”。

**H7 — 诊断默认给行动，不默认写脚本**
- 用户问“为什么不爆 / 账号怎么调 / 完整诊断”时，默认输出漏斗判断、对标差距、内容结构、视觉标准、复盘指标、P0/P1/P2 行动。
- 账号诊断必须同时看 top/bottom；同一机制至少在 2 条赢家中重复且未同样高频出现在 bottom，才叫账号公式。输出 `继续保持 / 从对标补齐 / 不要照抄` 和下一轮单变量测试。
- 只有用户明确说“下一条发什么 / 帮我写脚本 / 给案例”时，才写下一条可发布初稿或逐字脚本。
- 如果账号内容明显是 AI 视频 / AI 插画 / 数字人口播，必须加一节“AI 视频表达差距”：首帧冲突、人物连续性、场景连续性、字幕安全区、模板感、可信度、时长承载能力。

**H8 — PDF 按需，但排版要自检**
- 默认只写 `.md`。用户明确要 PDF 时再跑 `scripts/render_report_pdf.py`。
- PDF 报告避免超宽表格、手机长截图整张塞入、Markdown 表格包在 HTML 容器里。生成后至少检查文件存在、页数合理、图片没有明显丢失。

---

## 0. 闭环图

```
[我的原始素材（文档 / 图片 / 视频 / 非平台链接）]   ← 新入口（compose）
       │
       ▼ ⓪ compose (多模态解析 → 核心事实/独家要素/金句清单 → 5 维本质 → 信息缺口)
       │
[我的账号 / 选题方向 / compose 画像]
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
       ▼ ③ adapt  (有素材时：每个产出必须溯源到"对标公式 + 素材条目")
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
| "我有素材帮我写一条能爆的" / "这份文档/这组图/这段视频能出一条爆款吗" / "基于这些材料做一条" | **compose + find + crack + adapt**（素材打底全闭环） |
| "诊断这个带货账号" / "分析这个带货视频链接或文件" / "根据商品资料写带货脚本" | **commerce**（账号诊断 + 对标内容分析，见 §1B） |
---

## 1A. compose 命令 SOP（素材 → 初稿的新入口）

> **触发**：用户带着**自己的原始素材**（本地文档 / 图片 / 视频 / 非平台链接）+ 一句"帮我写一条能爆的"。
> **作用**：跑在 `find` 之前，把一堆散素材炼成"5 维本质 + 独家要素清单 + 信息缺口"，让下游 find/crack/adapt 有的放矢、且不乱编素材。

### 输入
- **必选** 1-N 份原始素材（任意组合）：
  - 本地文档 `.md` / `.txt` / `.pdf` → `scripts/analyze_document.py <path>`（md/txt 也可以直接 Read；pdf 走脚本）
  - 图片 `.jpg` / `.png` → `scripts/analyze_image.py`
  - 视频 `.mp4` / `.mov` → `scripts/analyze_video.py`
  - 非平台链接（文章 / 博客 / 新闻 / 自己的官网/产品页）→ `WebFetch` 取正文
- **必选**：我的账号定位（一句话）+ 目标平台
- **可选**：我想强调的卖点 / 情绪 / 必须保留的关键词
- **不走本命令**：小红书 / 抖音 / 快手 / 视频号 / B 站 / 公众号链接 — 那些是"别人的爆款"，直接走 `crack`

### Step 1 逐份解析（多模态必跑，跟 find Step 1 对称）

每份素材都跑一次对应脚本，**不要看一份就下结论**。汇总成**素材画像**，5 个字段：

| 字段 | 说明 | 来源要标到具体素材 |
|---|---|---|
| 核心事实 | 3-5 条原子事实 | 每条标 `[素材 X · 段落/时间戳]` |
| **独家要素** | 其他人没有的点：人物 / 数据 / 画面 / 场景 / 金句 | adapt 强制嵌入，必须标来源 |
| 视觉素材候选 | 图片 / 视频帧 / 文档配图 | adapt 的封面直接从这里挑 |
| 情绪基调 | 全部素材汇总出的情绪色 | 后续 Step 2 的 5 维输入 |
| **信息缺口** | adapt 想成立但素材没覆盖的点 | 明文列，**问用户**不要编 |

### Step 2 炼 5 维本质（复用 find Step 1 框架）

基于素材画像，按 `find` 的 5 维（载体形态 / 情绪锚点 / 审美风格 / 内容结构 / **反差点**）推断这条内容**应该长成什么样**。输出形容词三元组 + 一句话定位。

这 5 维直接喂给 `find` → **find 可以跳过自己的 Step 1**（已经有 5 维了），从 Step 2 矩阵搜索开始。

### Step 3 交棒 find → crack → adapt（素材模式）

后面三步的差异：

- `find`：跳过 Step 1，直接用 compose 的 5 维跑 Step 2-5
- `crack`：完全复用 SOP
- `adapt`（**素材模式，强制项**）：
  1. 标题 / 首段 / CTA 各至少嵌入 **1 条素材独家要素**
  2. 封面大字**优先**从素材画像的"候选金句"里选
  3. 每个产出除了现有的"抄了对标什么 + 改了什么"，**加一行** `用了素材：[素材 X · 具体要素]`
  4. 素材覆盖不到、只能走通用话术的位置，**必须 ⚪ 推断 标记** — 用户看到就知道这块是脑补
  5. 缺口明显影响成稿时（例：素材里没有具体数字但对标都有）→ **停下来问用户补**，不要编一个假数字

### compose 的输出

落盘到 `./reports/{YYYYMMDD-HHMM}-compose-{素材短码}.md`，含：
- 素材清单（文件名 + 字/帧/时长）
- 5 维本质 + 形容词三元组
- 独家要素清单（编号）
- 候选金句 / 视觉素材清单
- **信息缺口清单 → 给用户的补充素材请求**（如有）

完整闭环跑完后，adapt 报告里**必须含"素材溯源列"** — 没有这一列视同半成品，不写盘。

### compose 的铁律
1. **素材全吃完再下结论**：N 份素材全跑完解析再炼 5 维，不要跑到第 2 份就开写
2. **不编独家要素**（对齐全局 feedback `账号资料修改要斟酌` 的铁律 — 素材没给的不要凭空加）：adapt 想写但素材没给 → 问用户或标 ⚪ 推断
3. **素材优先于通用话术**：adapt 的每一行能从素材抠出来的，就不要用通用公式兜底
4. **每一行要能双向溯源**：对标公式（抄了什么）+ 素材条目（用了什么）两头都挂得上钩

---

## 1B. commerce 命令 SOP（账号诊断 + 对标内容分析）

> **作用**：复用本 Skill 的核心 `diagnostic/find/crack/adapt` 链路，诊断带货账号，解析平台带货视频链接或本地视频。用户要求诊断、差距或改进时，必须结合 3-5 条同类对标；只要求客观拆解时可先完成单条 `crack`。商品详情截图、SKU、资质文件和用户确认事实用于商品一致性检查与脚本生成。
> **不提供**：在线商品页解析、选品、趋势监控、GMV/佣金推断。视频链接与商品链接必须分开处理。

### commerce 输入门禁

检测到 commerce 请求后，按目标索要材料：

| 目标 | 必选输入 | 可选输入 |
|---|---|---|
| 诊断带货账号 | 账号主页链接；平台 | 后台指标截图/JSON、用户认可的对标账号 |
| 分析带货内容 | 平台视频链接或本地 `.mp4/.mov`；账号定位 | 商品详情/SKU/资质材料、后台指标、用户指定对标 |
| 生成带货脚本 | 商品名称；至少一份详情/SKU/资质/品牌资料；账号定位；目标人群 | 本地参考视频、表达风格、目标指标 |

- 平台视频链接：先复用通用 `crack` 的链接解析、详情和媒体下载链路；连续 3 次失败后，明确标记工具不可用并要求用户上传本地视频，不能假装看过画面。
- 抖音/小红书/快手/B 站可以接收各自支持的作品链接；视频号客户端没有普通可复制作品 URL，按账号名/关键词搜索或用户上传本地文件处理。
- `tikhub --health` 和工具出现在 `list` 中只证明客户端/目录正常，不证明业务接口能返回数据；必须以一次真实调用成功作为本次任务的能力门禁。
- 只有商品链接：说明本 Skill 不解析在线商品页，请用户上传详情页、SKU、价格活动和资质截图。
- 只有品类词并要求选品/趋势：说明不支持，不生成伪 Top10，也不推荐外部未安装能力。

### commerce 子命令

| 用户说什么 | 路由 |
|---|---|
| "诊断这个带货账号" / "账号为什么不出单" | **commerce-diagnostic**：通用三层诊断 + 带货内容维度 + 同赛道账号对标 |
| "分析这个带货视频链接或文件" / "检查这条素材" | **commerce-review**：链接解析/本地视频 → 多模态拆解 → 同类对标差距 + 风险 |
| "根据这些商品资料写带货脚本" / "这个品怎么拍" | **commerce-adapt**：用户证据 → ProductFactCard → 文案 + 分镜 |

### commerce-diagnostic：账号诊断叠加电商维度

先读取 `references/commerce-analysis-template.md`。完整复用 `references/diagnostic-mode.md` 的三层诊断，不能另造一套脱离对标的电商评分：

1. Layer 1：只用用户后台数据判断曝光、点击、完播、互动和商品点击漏斗；缺什么就标什么，不能估算。
2. Layer 2：用 `find` 搜索并筛出 3-5 个同平台、同品类、同内容形态、体量可比的账号。
3. Layer 3：抽样我方 top 3 + bottom 3、对标 top 3，全部跑多模态内容分析。
4. 在通用六维差距上追加：商品露出、利益点顺序、证明动作、信任建立、CTA、商品一致性和合规风险。
5. 从 top/bottom 与对标样本归纳内容赛道、账号相对赢家、重复钩子、重复证明方式、转化公式和复刻门槛；至少出现 2 次才叫账号公式。
6. 输出 `继续保持 / 从对标补齐 / 不要照抄` 和下一轮单变量测试；没有有效对标时只能交付部分诊断。

### commerce-review：视频链接/本地视频 + 对标审查

先读取 `references/commerce-analysis-template.md`。如果输入是平台视频链接，按 §7 的通用 `crack` 工具表解析分享链接、获取详情和媒体地址，下载到临时目录；输入已经是本地文件时直接进入多模态。媒体拿不到时不得只读标题和互动数据冒充完整内容分析。

1. 对目标视频运行 `scripts/analyze_video.py`，完成 4 维钩子与电商维度拆解。
2. 从目标视频提取品类、目标人群、载体形态、情绪锚点、内容结构、利益点与证明方式。
3. 用户只要求“拆解这条”时，可在目标视频完整多模态分析后交付单条 `crack`，并明确这是内容拆解、不是账号或效果诊断。
4. 用户要求“为什么不爆/不出单、哪里有问题、和同行差在哪、怎么改”时，必须复用 `find` Step 2-5 搜索候选，经多模态过滤后保留 3-5 条同类对标；用户已指定对标时直接 `crack`，但仍要校验是否同类。
5. 诊断型请求必须输出逐维横向比较和差距结论。对标搜索连续 3 次失败时标记为“部分（缺对标层）”，让用户补 3-5 条对标链接，不能输出伪对标。
6. 单条报告必须包含：证据/完整度、结果概览、完整口播、节拍映射、流量点、转化点、用户决策链、品类镜头、复刻框架卡、风险修正。

目标视频拆解格式：

```
钩子（4 维拆解）：
├ 视觉钩：...
├ 文字钩：...
├ 口播钩：...
├ 剧情钩：...
└ 综合：视觉 ×0.X + 口播 ×0.X = ...

电商 5 维（commerce 模式专属）：
├ 商品露出：出现时间点 + 露出方式（手持/桌面/对比/使用过程/开箱）
├ 利益点顺序：[痛点] → [产品引入] → [卖点1] → [证明动作] → [卖点2] → [CTA]
├ 转化链路：兴趣点（第 N 秒）→ 信任点（第 N 秒）→ 行动点（第 N 秒）
├ 商品卡一致性：仅在用户提供详情/SKU 证据时核对；否则写“未核验”
└ 复刻风险评估：
   ├─ ✅ 可复用：结构/话术/镜头语言
   ├─ ⚠️ 谨慎复用：需授权素材/真人出镜/品牌专属
   └─ ❌ 不可复用：版权内容/虚假宣传/平台违规

内容力：[0-10] 前 3 秒钩子强度
转化点：[0-10] 推动商品卡点击的结构设计（不是实际转化率）
```

对标差距至少覆盖：前 3 秒、商品首次露出、利益点数量与顺序、证明动作、信任点、CTA、评论反馈和复刻成本。每个结论必须指向目标视频时间戳与至少一条对标证据。

不得根据公开互动或视频内容推断销量、GMV、佣金、商品点击率和成交转化率。

### commerce-adapt：强制读取商品事实卡

`adapt` 在 commerce 模式下，**必须先读取或构建 ProductFactCard**，不能直接用通用文案公式：

```
ProductFactCard（adapt 的前置输入）：
├─ 商品名称（必填）
├─ 商品链接（可选，仅记录，不自动抓取）
├─ 商品事实（3-5 条原子事实，每条有来源）
├─ SKU（名称 / 价格 / 库存状态；拿不到就留空并列入待核验）
├─ 目标人群（年龄段/性别/需求场景）
├─ 用户痛点（3 条，按强度排序）
├─ 产品卖点（3-5 条，有详情页证据）
├─ 用户买点（3 条 — 为什么用户会下单）
├─ 证明动作（可拍摄的演示/对比/实验）
├─ 可用文案（已核验的事实 → 可直接写的句子）
├─ 禁用表达（功效承诺/绝对化用语/价格误导/未授权声称）
├─ 价格与活动条件（含资料确认时间）
├─ 资质与授权状态
└─ 待核验项（页面打不开/矛盾信息/缺少证据的点）
```

**commerce-adapt 的铁律**（在现有 adapt 铁律基础上追加）：
- 文案只能引用 ProductFactCard 中**已核验**的事实
- 没有证据的功效、数量、价格、赠品和效果 → **必须标成 `⚠️ 待核验`**，不得写成确定性文案
- 每个卖点必须能回指到：用户上传的详情页截图/资质文件/品牌资料/用户确认信息
- 价格、库存、赠品、活动期限必须标记资料确认时间
- ProductFactCard 证据不足时停止并列出需要补充的材料，不生成确定性脚本

### commerce-adapt 的输出格式

```markdown
## 标题候选（3 个，每个标注命中哪个标题公式 + 用了哪个商品利益点）
  1. 「[文案]」 — 公式 N + 利益点「XXX」+ 改了 XX
  2. 「[文案]」 — 公式 N + 利益点「XXX」+ 改了 XX
  3. 「[文案]」 — 公式 N + 利益点「XXX」+ 改了 XX

## 口播脚本（15s / 30s / 60s 三档）
  15s：「[口播全文]」— 只打 1 个核心利益点 + CTA
  30s：「[口播全文]」— 痛点 → 1 个利益点 + 证明 + CTA
  60s：「[口播全文]」— 痛点 → 2-3 个利益点 + 证明动作 + 价格/赠品 + CTA

## 分镜提示（3-5 镜）
  镜1：[时间] [画面描述] [口播对应句] [商品露出方式]
  镜2：...
  ...

## CTA 候选（2 个）
  1. 「[文案]」— 限时/限量/评论互动
  2. 「[文案]」— 引导主页/直播间/商品卡

## 风险标注
### ⚠️ 待核验
- [列出所有未核实的事实；没有则写“无”]
### 🚫 禁用表达
- [列出 ProductFactCard 标记的禁用项；没有则写“无”]
价格确认时间：[时间戳]
```

落盘 JSON 前必须运行 `build_commerce_package.py`。脚本返回 `invalid` 时修复报告或补证据，不得交付旧 JSON；成功包契约版本为 `2.0.0`。

### commerce 的输出位置

commerce 模式跑完，落盘到：

```
./reports/
  commerce-diagnostic-{YYYYMMDD-HHMM}.md # 带货账号三层诊断 + 对标差距
  commerce-review-{YYYYMMDD-HHMM}.md     # 视频链接/本地视频拆解；诊断型请求含对标差距
  commerce-adapt-{YYYYMMDD-HHMM}.md      # 带货文案+分镜+风险标注
  product-fact-{YYYYMMDD-HHMM}.md        # 商品事实卡
```

### commerce 的铁律
1. **不编商品事实**：用户没有上传证据就不能猜；材料内部矛盾时先列冲突，不生成文案
2. **每个卖点可溯源**：必须能回指到用户上传材料的文件名 + 页码/截图/行号
3. **禁用表达前置**：文案生成前先列出哪些话不能说（功效承诺/绝对化/价格误导）
4. **价格有时效**：价格、库存、赠品、活动期限必须标记资料确认时间
5. **合规不是可选项**：带货文案必须标注风险项，禁止把"待核验"写成确定性表达

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
- 小红书 `xiaohongshu_app_v2_search_notes`
- 抖音优先 `douyin_billboard_fetch_hot_account_search_list --cursor 0` 找账号；再用 `douyin_search_fetch_challenge_search_v2` → `douyin_app_v3_fetch_hashtag_video_list` 反查作者；`douyin_search_fetch_video_search_v2` 只做补充且必须加超时
- 快手 `kuaishou_app_search_video_v2`
- 视频号 `wechat_channels_v2_fetch_search_channel_videos`

**接口失败兜底**：客户端完成 3 次退避重试仍失败 → 不再重复计费调用，让用户提供 3-5 个对标链接或本地素材 → 直接走作品详情 → 跳到 crack。

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
  {YYYYMMDD-HHMM}-compose-{素材短码}.md        # compose 模式才有：素材画像 + 5 维 + 缺口清单
  {YYYYMMDD-HHMM}-find-{我的账号末8位}.md      # 5-10 对标 + 为什么是真对标
  {YYYYMMDD-HHMM}-crack-{对标末8位}.md         # 每条 4 行清单
  {YYYYMMDD-HHMM}-adapt-{选题短码}.md          # 标题 + 封面 + 首段 + CTA（compose 模式必须含"素材溯源列"）
  commerce-diagnostic-{YYYYMMDD-HHMM}.md       # commerce 模式：带货账号诊断 + 对标差距
  commerce-review-{YYYYMMDD-HHMM}.md           # commerce 模式：视频链接/本地视频 + 对标审查
  commerce-adapt-{YYYYMMDD-HHMM}.md            # commerce 模式：带货文案+分镜+风险标注
  product-fact-{YYYYMMDD-HHMM}.md              # commerce 模式：商品事实卡

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
- 结构化 fallback 同样支持本地关键帧画廊；同一段连续放 1-3 张 Markdown 图片时自动横向排版并保留图片 alt 作为图注
- 富排版（卡片式 top N 对标 / TL;DR 红框 / 三图横排）需在 md 里**直接写 inline HTML**，CSS 已经准备好对应 class：
  - `<div class="tldr"><div class="verdict">...</div>...</div>` — TL;DR 高亮框
  - `<div class="card"><div class="card-img"><img/></div><div class="card-body">...</div></div>` — 对标卡片
  - `<div class="user-img"><img/><div class="caption">...</div></div>` — 三图横排
- 想保留中间 HTML 自己改样式：加 `--keep-html`

**客户版 PDF 内容铁律**：
- PDF 是分析交付，不是运行日志。不得出现执行命令、脚本/API/模型名、绝对路径、JSON/TXT 文件名、临时目录、技术状态码或“素材证据包”。
- 单条视频至少选 4-6 张覆盖开头、中段和结尾的关键帧。每张图注必须写“时间点 + 画面任务”，并在相邻正文说明它服务于钩子、卖点、证明、场景还是 CTA；不能只堆截图。
- 默认结构：一页结论 → 关键画面链 → 节拍/文案逻辑 → 流量逻辑 → 转化逻辑 → 可复刻路径 → 风险与单变量实验。
- 默认不放完整逐字稿，只摘与结构判断相关的关键句。用户明确要逐字稿时再放附录。
- 技术证据和产物路径留在内部 `.md`/运行目录；PDF 只呈现用户做内容决策所需的信息。

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

> 调用走 `tikhub <platform> <endpoint> --args`。CLI 自包含在仓库 `tikhub/` 目录，底层直接请求 TikHub REST API（`https://api.tikhub.io/api/v1/...`），**禁止调用 TikHub MCP 或 `mcp.tikhub.io`**。不知道端点名时用 `tikhub list <platform> <关键词>`；看 HTTP 方法、REST 路径和参数 schema 用 `tikhub describe <platform> <endpoint>`。

**参数类型铁律（防"看着对其实数据被破坏"）**：
- CLI 默认所有 `--key=value` **按 string 透传**，只 `true/false/null/none` 字面量被 coerce
- ID 字段（`user_id` / `photo_id` / `note_id` / `sec_user_id` / `aweme_id`）几乎都是 string schema — **直接 `--user_id 4253294011`**，不要包 `:int`
- 真要 int 用显式 tag：`--page:int=1` / `--count:int=20`；复杂结构用 `--json '{...}'`
- 看到 `validation error ... input_type=int` → 检查是不是手贱加了 `:int`

| 任务 | 小红书 | 抖音 | 快手 | B 站 |
|---|---|---|---|---|
| **find Step 3 关键词搜** | `xiaohongshu_app_v2_search_notes`（笔记） / `xiaohongshu_app_v2_search_users`（用户） | `douyin_billboard_fetch_hot_account_search_list --cursor 0`（账号优先） / `douyin_search_fetch_challenge_search_v2`（话题） / `douyin_search_fetch_video_search_v2`（视频补充） | `kuaishou_app_search_video_v2` | `bilibili_web_fetch_general_search` |
| **find Step 5 账号信息** | `xiaohongshu_app_v2_get_user_info` | `douyin_app_v3_handler_user_profile` | `kuaishou_app_fetch_one_user_v2` | `bilibili_web_fetch_user_profile` + `_user_up_stat` + `_user_relation_stat` |
| **crack 笔记/视频详情（最稳兜底）** | `xiaohongshu_web_v3_fetch_note_detail` / `xiaohongshu_app_v2_get_video_note_detail` | `douyin_app_v3_fetch_one_video` | `kuaishou_app_fetch_one_video` | `bilibili_web_fetch_one_video` |
| **crack 拿封面/视频** | 用笔记详情返回的 `image_list` URL；不要用已挂的独立 image 接口 | `douyin_app_v3_fetch_video_high_quality_play_url` | `kuaishou_app_fetch_one_video`（含 play_url） | `bilibili_web_fetch_video_subtitle`（字幕拆口播） |
| **crack 拿评论** | `xiaohongshu_app_v2_get_note_comments` | `douyin_app_v3_fetch_video_comments` | `kuaishou_web_fetch_one_video_comment` | `bilibili_web_fetch_video_comments` + `_comment_reply` |
| **B 站独家：弹幕** | — | — | — | `bilibili_web_fetch_video_danmaku`（4 类信号见 platforms/bilibili.md §3） |
| **解析分享链接** | `xiaohongshu_web_v3_fetch_note_detail`（支持分享文本时直接传） | `douyin_app_v3_fetch_one_video_by_share_url` | `kuaishou_web_fetch_one_video_by_url` | `bilibili_web_bv_to_aid`（bv ↔ aid 转换） |

### 视频号（独立路径 — 没分享链接）

视频号客户端**不输出可复制的链接 / 视频 ID**（分享出去是卡片，不是 URL）。所以任何视频号任务的入口都是**账号名/关键词搜索**，跟其他三平台流程不一样：

| 任务 | 工具 | 注意 |
|---|---|---|
| **find Step 3 关键词搜** | `wechat_channels_v2_fetch_search_channel_videos` | 按关键词发现视频号作品 |
| **find Step 5 账号信息** | `wechat_channels_v2_fetch_user_profile` | 从搜索或详情取得 `username` 后调用 |
| **账号作品列表** | `wechat_channels_v2_fetch_user_videos` | 用真实作品样本做账号内排序 |
| **crack 视频详情** | `wechat_channels_v2_fetch_video_detail` | 拉取公开互动与媒体字段 |
| **crack 拿评论** | `wechat_channels_v2_fetch_video_comments` | — |
| **直播回放** | `wechat_channels_v2_fetch_live_history` | — |

**视频号 find 调整**：先用关键词搜索拿到真实作品，再从作品详情识别账号并调用用户资料/作品列表；不要用昵称相似代替账号身份校验。

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
- `analyze_image.py <封面1> [封面2 ...] [--concurrency 1] [--timeout 600]`：拿 5 变量 + 5 模板归类 + 钩子识别；支持多图批量，默认串行，确认额度充足时再手动调高并发
- `analyze_video.py <视频> [--mode auto/talking/visual/keyframe]`：三模式自动路由；visual/talking 默认按视频配置走，本地片段存在且未禁用时发 video_url；设 `VIDEO_ANALYSIS_USE_VIDEO_URL=0` 或没有可用视频片段时才走代表帧兜底
- `analyze_document.py <文档> [--json]`：compose 用，吃 `.md` / `.txt` / `.pdf` → 全文 + 章节 + 候选金句 + 字数；PDF 依赖 pdfplumber / pypdf / fitz / pdftotext 任一（四选一，都没有时会提示装）
- `ocr_screenshot.py <截图>`：用户给后台数据截图时用；非 JPEG 默认转 JPEG，可用 `VIDEO_ANALYSIS_NORMALIZE_IMAGES=0` 关闭
- `dispatch_account.py <账号URL>`：链接 → platform + user_id
- `render_report_pdf.py <md> [-o out.pdf] [--keep-html]`：md 报告 → PDF（**按需，不默认**，详见 §5.1）
- `normalize_metrics.py <input.json> [--platform douyin/kuaishou/xhs] [--baseline account_id]`（commerce 模式）：跨平台指标归一化，输出账号基线倍数和增长异常标记。按粉丝规模分桶（0-1k/1k-10k/10k-100k/100k+），取同类账号中位数做基线
- `build_commerce_package.py <product_fact.md> <adapt_output.md> [--output commerce-package.json]`（commerce 模式）：按 ProductFactCard 2.0 契约校验并打包；关键字段缺失时不写输出文件

### commerce 参考文件（references/）
- `references/commerce-workflow.md`：commerce 模式账号诊断、视频链接解析、对标分析与事实卡流程
- `references/commerce-analysis-template.md`：commerce 单条/账号报告的证据标签、流量点、转化点、品类镜头、复刻卡和质量门禁
- `references/commerce-metrics.md`：带货视频核心指标（ECPM/点击率/转化率/商品点击率）、各平台带货阈值经验值、内容力/流量点/转化点评分标准
- `references/product-video-framework.md`：商品展示配方（开箱/对比/使用过程/口播种草/剧情带货）、镜头语言、商品露出时机和方式的最佳实践
- `references/platforms/douyin-commerce.md`：抖音电商专属规则 — 商品卡规范、千川低质素材避坑、商品三一致要求、禁用表达清单

---

## 9. 接口稳定性表（按平台分小节）

### 9.1 小红书（REST OpenAPI V5.3.2，2026-08-14 刷新）

> 只使用当前 `/openapi.json` 目录中存在的 REST 端点。旧 App V1、Web V1、Web V2 名称已经不在当前目录中，不再调用，也不再沿用旧 MCP 时期的稳定性结论。

| 任务 | ✅ 首选 | ⚠️ 备选 | ❌ 不要用 |
|---|---|---|---|
| **关键词搜笔记** | `xiaohongshu_app_v2_search_notes` | `xiaohongshu_web_v3_fetch_search_suggest` 只用于扩词 | 目录外旧端点 |
| **关键词搜用户** | `xiaohongshu_app_v2_search_users` | — | 目录外旧端点 |
| **图文/视频笔记详情** | `xiaohongshu_app_v2_get_image_note_detail` / `xiaohongshu_app_v2_get_video_note_detail` | `xiaohongshu_web_v3_fetch_note_detail`（需 note_id + xsec_token） | 目录外旧端点 |
| **笔记评论/二级评论** | `xiaohongshu_app_v2_get_note_comments` / `xiaohongshu_app_v2_get_note_sub_comments` | — | 目录外旧端点 |
| **账号信息** | `xiaohongshu_app_v2_get_user_info` | `xiaohongshu_web_v3_fetch_user_info` | 目录外旧端点 |
| **用户作品列表** | `xiaohongshu_app_v2_get_user_posted_notes` | — | 目录外旧端点 |
| **拿封面/图片** | 用详情响应中的媒体 URL | — | 独立抓图旧端点 |
| **分享文本** | App V2 详情/账号端点的 `share_text` 参数 | — | 旧解析器端点 |

**铁律**：
- ✅ 每次以 `tikhub list xiaohongshu` 和 `tikhub describe` 的当前目录/schema 为准
- ❌ 端点经客户端 3 次退避重试仍失败 → 换目录内备选或让用户补截图/素材，不手工循环调用
- ❌ 小红书不支持按话题标签搜索笔记，只支持关键词；用户问“搜 #XX 标签”时说明限制
- 📅 OpenAPI 目录有版本变化时重新运行 `tikhub/scripts/refresh_tools.py xiaohongshu`

**并发与限流（实测 2026-04-21）**：
- 官方文档标注 QPS 10；账号诊断建议并发不超过 3，429 交给 REST 客户端退避重试。

### 9.2 视频号（REST OpenAPI V5.3.2，2026-08-14 刷新）

| 任务 | ✅ 用这个 | ⚠️ 注意 |
|---|---|---|
| 关键词搜作品 | `wechat_channels_v2_fetch_search_channel_videos` | 从真实作品识别账号 |
| 账号信息 | `wechat_channels_v2_fetch_user_profile` | 需要 `username` |
| 用户作品 | `wechat_channels_v2_fetch_user_videos` | 用于账号内 top/bottom 排序 |
| 视频详情 | `wechat_channels_v2_fetch_video_detail` | 以当前 schema 为准 |
| 评论列表 | `wechat_channels_v2_fetch_video_comments` | — |
| 直播回放 | `wechat_channels_v2_fetch_live_history` | — |

**视频号铁律**：
- ❌ **不要让用户提供视频号链接 / 视频 ID** — 视频号客户端只支持卡片分享，根本不输出 URL/ID
- ✅ 搜索结果必须通过作品详情里的账号标识回查，不能只靠昵称相似判断同一账号
- ✅ 冷启结论至少需要账号作品列表和多条公开互动，不能用单条作品直接判死
- 📅 OpenAPI 目录有版本变化时重新刷新 wechat 目录

### 9.3 抖音（局部复测 2026-06 — 对标搜索优先走账号搜索）

🟡 **状态**：抖音找对标不要只依赖视频搜索。`douyin_billboard_fetch_hot_account_search_list --keyword <词> --cursor 0` 可用于账号搜索；视频搜索只做补充并设置调用超时。

**实测命令**（用 tikhub CLI）：
```bash
tikhub --health
tikhub list douyin search
tikhub douyin douyin_billboard_fetch_hot_account_search_list \
  --keyword 宝宝情绪 --cursor 0
tikhub douyin douyin_search_fetch_challenge_search_v2 \
  --keyword 宝宝情绪 --cursor 0 --count 10
tikhub douyin douyin_search_fetch_video_search_v2 \
  --keyword 宝宝情绪 --offset 0 --count 10
```

| 任务 | 实测结果 | 备注 |
|---|---|---|
| `douyin_billboard_fetch_hot_account_search_list` | 可用 | 找账号对标首选；`cursor` 必传 |
| `douyin_search_fetch_challenge_search_v2` | 当前目录存在 | 可先找话题，再拉话题视频反查作者 |
| `douyin_search_fetch_video_search_v2` | 当前目录存在 | 加超时，失败后换账号/话题搜索 |
| `douyin_web_handler_user_profile` | 可用 | 适合拿公开主页基础信息 |
| `douyin_web_fetch_user_post_videos` | 部分受登录限制 | 普通号可能返回空，必要时结合后台截图 |

**推荐调用顺序（找对标时）**：
1. 从账号简介和近 10 条作品提取 4-6 个关键词
2. 账号搜索首选 `douyin_billboard_fetch_hot_account_search_list --cursor 0`
3. 账号搜索不够时，用 `douyin_search_fetch_challenge_search_v2` 拿 `ch_id`，再用 `douyin_app_v3_fetch_hashtag_video_list --ch_id <id>` 反查高互动作者
4. 视频搜索只做补充；超时 1 次就换账号搜索或话题搜索，不要连续卡住
5. 新号优先找 3-5 个 500-1W 粉的同赛道号，再补 1-2 个更高粉账号看方法论

**不要误判为无对标的情况**：
- 某个 search 工具 schema 为空 / 参数不明：先 `tikhub list douyin search` 或 `tikhub describe` 查清楚
- 视频搜索挂了但账号搜索可用：L2 仍可完成
- 用户给的是短链：先解析 `sec_uid` / `aweme_id`，再用主页信息提关键词

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
| `kuaishou_app_fetch_video_comment` | 待测 | — |
| `kuaishou_web_fetch_one_video_by_url` | 待测 | — |

---

1. **find 必须 5 步走**：本质识别 → 矩阵搜 → 多模态过滤 → 体量过滤 → 人工勾选。任何一步都不能省。
2. **不要单一宽泛词搜对标**（如"东北大酱"）。永远是 4-6 个本质维度词矩阵。
3. **search 关键词必须是单一中文词，2-4 字最稳，禁止空格组合**（带空格的组合词在 V1/V2 接口都易 HTTPStatusError — 拆成多个单词分次搜更稳）。
4. **crack 输出 4 维钩子拆解**（视觉/文字/口播/剧情 + 综合权重），不是单句钩子。综合权重决定仿写时的精力分配。
5. **adapt 必须命中 scoring-vocab.md 公式**，且必须标注"抄了什么 + 改了什么"。
6. **诊断不主推**。除非用户明确说"为什么不爆"，否则不要走 L2。
7. **multimodal 不省**：find Step 1 看我的、find Step 4 看候选 — 都要调。token 贵但不能省。
   - 退化兜底：媒体 URL 不可用时，只能用详情返回的标题、描述、标签做文本层推断，**必须明文标注“未完成视觉验证”**，不能输出封面模板结论。
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

11. **TikHub 只走直接 REST API，不走 MCP**：所有数据抓取通过 `tikhub <platform> <endpoint> --args` CLI 调用；CLI 直接请求 `https://api.tikhub.io/api/v1/...`，使用 Bearer API key。**禁止请求 `mcp.tikhub.io`，禁止 `claude mcp add tikhub-*`，禁止任何 TikHub MCP 工具调用**。

    - 非中国大陆默认基础域名：`https://api.tikhub.io`
    - 中国大陆可设置：`TIKHUB_API_BASE_URL=https://api.tikhub.dev`
    - REST 端点目录来自公开 `openapi.json`，用 `python3 tikhub/scripts/refresh_tools.py` 刷新
    - 不需要 MCP session、初始化握手或 session 缓存

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
