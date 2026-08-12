# commerce-workflow — 带货电商模式完整工作流

> 本文件是 SKILL.md 的 commerce 模式（§1B）的详细参考。
> 定义 commerce 子命令的路由规则、完整工作流、以及与其他 Skill 的调用协议。

---

## 0. commerce 模式总览

```
[商品链接 / 账号定位 / 目标人群]
       │
       ▼ ⓪ commerce-product（商品事实卡构建）
[ProductFactCard]
       │
       ▼ ① commerce-find（基于商品本质找带货对标）
[5-10 个带货对标爆款]
       │
       ▼ 人工勾选 3-5 条 ✋
[选定对标]
       │
       ▼ ② commerce-crack（4 维 + 电商 5 维拆解）
[带货爆款拆解报告]
       │
       ▼ ③ commerce-adapt（强制读取 ProductFactCard）
[标题 + 口播脚本 + 分镜 + CTA + 风险标注]  → 可拍
```

---

## 1. 子命令路由规则

### 触发词分类

| 触发词类别 | 关键词 | 默认路由 |
|---|---|---|
| 商品分析 | 商品链接、详情页、这个品、产品分析、卖点、利益点 | commerce-product |
| 带货找对标 | 带货对标、同类商品爆款、带货爆款视频、找带货账号 | commerce-find |
| 带货拆解 | 拆带货爆款、这条带货为什么爆、带货视频拆解 | commerce-crack |
| 带货文案 | 写带货文案、带货脚本、商品文案、口播脚本、分镜 | commerce-adapt |
| 选品 | 选品、今天拍什么、Top10、选品建议 | commerce-selection |
| 综合 | 带货视频怎么拍、这个品怎么卖、帮我做一条带货 | commerce-product → commerce-find → commerce-crack → commerce-adapt（全闭环） |

### 路由决策树

```
用户输入
├─ 包含商品链接？
│  ├─ 是 → 先 commerce-product（构建 ProductFactCard）
│  │       └─ 用户还想找对标？ → commerce-find
│  │       └─ 用户只想分析商品？ → 输出 ProductFactCard，结束
│  └─ 否 → 询问商品链接（commerce 模式必须）
│
├─ 包含带货对标需求？
│  ├─ 是 + 已有 ProductFactCard → commerce-find（用商品本质搜索）
│  └─ 是 + 无 ProductFactCard → 先 commerce-product，再 commerce-find
│
├─ 包含带货视频链接？
│  ├─ 是 → commerce-crack（拆指定视频）
│  └─ 否 + 需要拆解 → commerce-find 后人工勾选，再 commerce-crack
│
├─ 包含文案/脚本需求？
│  └─ 必须已有 ProductFactCard + crack 输出 → commerce-adapt
│
└─ 包含选品需求？
   └─ 需要 AccountProfile + 商品池 + 趋势数据 → commerce-selection（建议调外部 Skill）
```

---

## 2. commerce-product 子流程详解

### 目标

```
商品链接 → 商品事实卡（ProductFactCard）→ 利益点树 → 内容切入角度 → 风险清单
```

### 输入

- 商品详情页链接（必选）
- 商品图片/视频（可选，可从详情页抓取）
- SKU/规格信息（可选，可从详情页提取）
- 品牌/资质资料（可选）
- 达人账号画像（可选，用于人群匹配）

### Step 1：提取 product_id 并验证链接

```
1. 从商品链接中提取 product_id（正则: /goods/(\d+) 或 /product/(\d+)）
2. 调 TikHub douyin_web_fetch_product_detail 验证商品可访问
3. 保存 API 返回 + 抓取时间戳
4. 如果 API 返回空/报错 → 要求用户提供截图或手动输入商品信息
```

### Step 2：通过 TikHub API + WebFetch 兜底提取商品基础信息

**主路径 — TikHub API（6 个工具覆盖）**：

| 工具 | 获取内容 |
|---|---|
| `douyin_web_fetch_product_detail` | 商品标题、品牌、类目、主图、详情图 |
| `douyin_web_fetch_product_sku_list` | SKU 列表（规格/颜色/尺寸/价格） |
| `douyin_web_fetch_product_coupon` | 券后价、满减/优惠条件 |
| `douyin_web_fetch_product_review_score` | 好评率、各项评分 |
| `douyin_web_fetch_product_review_list` | 用户评价（前 50 条，用于痛点分析） |
| `douyin_web_fetch_live_room_product_result` | 直播间商品信息（如有直播场景） |

**兜底路径 — WebFetch**：

当 TikHub API 缺字段时，用 WebFetch 直接抓详情页 HTML 补充：
- 商品详情图/视频（下载媒体文件）
- 问大家/常见问题（⚠️ 通常 JS 渲染，WebFetch 可能拿不到）

**最终兜底**：要求用户提供截图或手动输入缺失信息。详细策略见 `references/platforms/douyin-commerce.md` §7。

### Step 2.1：提取 author_id / sec_user_id

商品 API 部分需要 `author_id` / `sec_user_id`（如 SKU 列表、优惠券）：
- 从用户提供的达人主页 URL 提取 sec_user_id（正则：`/user/(MS4wLjABAAAA[\w-]+)`）
- 如无达人 URL，调 `douyin_search_fetch_user_search` 搜索品牌/店铺名获取

### Step 3：生成事实层

```
事实卡：
├─ 3-5 条原子事实（每条标注来源：详情页第 N 屏/评价/资质文件）
├─ 规格参数表
├─ 价格与活动（含抓取时间）
└─ 冲突标记（详情页内部矛盾点）
```

### Step 4：推导卖点/痛点/买点

| 层次 | 定义 | 来源 |
|---|---|---|
| 卖点 (Selling Point) | 产品有什么 | 详情页 + 品牌资料 |
| 痛点 (Pain Point) | 用户为什么需要 | 评价 + 问大家 + 行业知识 |
| 买点 (Buying Point) | 用户为什么下单 | 卖点 ∩ 痛点 + 情绪驱动 |

### Step 5：生成证明动作

每个核心卖点 → 一个可拍摄的证明动作：
- 对比实验（使用前/后）
- 材质/成分展示
- 使用过程演示
- 数据/证书展示
- 真实用户反馈

### Step 6：生成风险清单

- 禁用表达（功效承诺/绝对化/价格误导/未授权声称）
- 待核验项（页面信息不完整/矛盾/缺少资质）
- 行业特殊限制（医疗/食品/化妆品/母婴/宠物/金融）

### 输出格式

```json
{
  "product_url": "",
  "captured_at": "",
  "facts": [
    {"fact": "", "source": "", "confidence": "confirmed/inferred/unknown"}
  ],
  "target_audience": [],
  "pain_points": [],
  "selling_points": [],
  "buying_points": [],
  "proof_actions": [],
  "price_and_gifts": [],
  "qualifications": [],
  "risky_claims": [],
  "pending_verification": [],
  "evidence": []
}
```

---

## 3. 与其他 Skill 的调用协议

### 输入协议（谁可以调用 social-account-doctor commerce 模式）

| 调用方 | 提供的数据 | 调用的 commerce 子命令 |
|---|---|---|
| commerce-trend-radar | TrendSnapshot（视频链接 + 指标快照） | commerce-crack（拆解预爆款） |
| commerce-product-intelligence | ProductFactCard | commerce-adapt（生成带货文案） |
| commerce-selection-advisor | AccountProfile + ProductFactCard[] + TrendSnapshot | commerce-find（找对标参考） |
| capsule-cinema | ProductFactCard + ScriptPackage | 不直接调用 — 由 adapt 输出 ScriptPackage 后再交 capsule-cinema |
| self-media-compliance-review | 脚本/视频/商品链接 | 不直接调用 — adapt 输出后交合规审核 |

### 输出协议（commerce 模式产出什么给其他 Skill）

| 输出 | 接收方 | 格式 |
|---|---|---|
| ProductFactCard | commerce-adapt, commerce-selection-advisor | JSON + MD |
| CrackReport（含电商 5 维） | commerce-trend-radar, commerce-selection-advisor | MD |
| ScriptPackage（标题 + 口播 + 分镜 + CTA + 风险标注） | capsule-cinema, self-media-compliance-review | MD + JSON |
| CommerceFindReport（带货对标列表） | commerce-selection-advisor | MD |

### 公共数据契约

几个 Skill 必须使用同一套对象结构，详见 `references/commerce-metrics.md` 末尾的数据契约章节：

- `AccountProfile`：账号画像
- `ProductFactCard`：商品事实卡
- `TrendSnapshot`：趋势快照
- `ComplianceReport`：合规报告

---

## 4. 最小可行版本（第一版边界）

### 第一版做到

- ✅ 输入商品链接 → 输出带证据的利益点分析
- ✅ 输入带货视频链接 → 输出带货结构拆解（4 维 + 电商 5 维）
- ✅ 基于 ProductFactCard + 对标拆解 → 输出 15/30/60 秒文案和分镜
- ✅ 根据用户指定类目 → 生成带货对标候选清单
- ✅ 报告保存到本地

### 第一版不承诺

- ❌ 100% 违规检测（那是合规 Skill 的职责）
- ❌ 任何平台都能稳定抓取
- ❌ 自动下载的素材都可以商用
- ❌ 全自动生成无需人工拍摄的爆款视频
- ❌ 实时价格/库存监控（那是 trend-radar 的职责）

---

## 5. 错误处理

| 场景 | 处理方式 |
|---|---|
| 商品链接打不开 | 要求用户提供截图或手动输入商品信息，不能猜 |
| 详情页信息矛盾 | 列出冲突点，不生成文案，等用户澄清 |
| 没有对标搜索结果 | 让用户手甩 3-5 个对标链接 → 直接进 crack |
| 商品涉及高风险行业（医疗/金融等） | 在 ProductFactCard 风险清单中标红，建议先跑合规审核 |
| 用户只给了商品链接没给账号信息 | 先分析商品，再追问账号定位和目标人群 |

---

## 6. 后续迭代方向

1. 接入 `commerce-product-intelligence` 做更深度的商品分析（评价 NLP、竞品对比、行业基准价）
2. 接入 `commerce-trend-radar` 获取实时趋势数据辅助选品
3. 接入 `commerce-selection-advisor` 做自动 Top10 选品
4. 将 ScriptPackage 直接喂给 `capsule-cinema` 做视频生成
5. 将合规检查嵌入 adapt 流程（调用 `self-media-compliance-review`）
