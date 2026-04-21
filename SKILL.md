---
name: account-diagnostic
description: >
  抖音 / 小红书 / 快手「账号 + 内容」自包含诊断引擎 — 用户给一张笔记数据截图（可选笔记链接），
  或给一对「我方账号 + 对标账号」链接，自动跑「输入路由 → tikhub 数据抓取 → Gemini 多模态视觉/视频分析
  → 三层诊断（漏斗自检 → 对标扫描 → 六维拆解）→ 平台子手册套用 → 行动建议」流水线。
  本 skill 完全自包含，不依赖任何其他 skill —
  搜索/账号信息走 tikhub MCP（mcp__tikhub-douyin / mcp__tikhub-xiaohongshu / mcp__tikhub-kuaishou），
  截图 / 封面 / 视频走 Gemini 3.1 Pro 多模态（VIDEO_ANALYSIS_API_KEY），
  评分术语在本 SKILL.md §5 自带（五种封面 / 10 标题公式 / 三骨架 / 七钩子）。
  覆盖三大平台两大主诊断逻辑：①漏斗指标诊断（平台经验阈值，比如抖音 5s完播率 ~50% 是行业合格线，详见 platforms/*.md）
  ②对标差距诊断（同赛道 5k-50k 粉对标账号，6 维拆解我 vs 对标）。
  当用户说"帮我诊断这个账号"、"看看我这条笔记为什么不爆"、"我和这个对标账号差在哪"、
  "这个号该往哪个方向调"、"帮我找几个对标账号分析"时调用。
metadata:
  author: tech_media_plan
  version: "0.3.0"
  uses_env:
    - VIDEO_ANALYSIS_API_KEY        # Gemini 3.1 Pro，给截图 OCR + 封面拆解 + 视频分段分析用
    - VIDEO_ANALYSIS_BASE_URL
    - VIDEO_ANALYSIS_MODEL_NAME
    - AUDIO_TRANSCRIPTION_API_KEY   # 可选 — SenseVoice 视频音轨转写（用了视频分析才需要）
    - AUDIO_TRANSCRIPTION_BASE_URL
    - AUDIO_TRANSCRIPTION_MODEL
  external_deps:
    - python3 (>=3.9)
    - requests
    - ffmpeg / ffprobe (可选 — 仅视频分析需要)
  platforms:
    - 抖音 (mcp__tikhub-douyin)
    - 小红书 (mcp__tikhub-xiaohongshu)
    - 快手 (mcp__tikhub-kuaishou)
---

# account-diagnostic — 账号 / 内容诊断引擎（自包含版）

> 截图 / 链接进，**「卡在哪一层 + 怎么调」**的可执行诊断报告出。
> 不是 "AI 看了下你的账号觉得还行"，是 **平台专属阈值 × 对标差距 × 可抄模板** 的三段式判决书。
> **本 skill 完全自包含**：tikhub MCP 调数据 + Gemini 多模态做拆解 + 本文档自带评分术语。

---

## 0. 内容时效性说明（先读这个）

本 skill 的内容按时效性分四档，**使用 / 维护时按档处理**：

| 档 | 内容 | 时效 | 维护策略 |
|---|---|---|---|
| **A. 永不过时** | §1 三层诊断框架、§5 评分术语（5 封面/10 标题/3 骨架/7 钩子）、§3 视频分析三 mode、平台调性定性结论 | 基于人性 + 方法论，多年稳定 | 不动 |
| **B. 季度级波动** | platforms/*.md 里所有具体数字（完播率、CTR、CES 系数、互动率、搜索占比等） | 平台算法迭代会改，半年内可能偏移 ±20% | **采集日期：2026-04**；建议每 6 个月用 §0 数据来源重新校准一次 |
| **C. 可能随时失效** | tikhub MCP 工具名（§8 速查表）、抖音星图 API "仅星图收录账号"限制、平台后台截图 OCR 字段名 | API 升级或平台改版即失效 | **最后核对：2026-04**；调用前先用 1 个测试账号验证工具能跑通 |
| **D. 高风险主张（默认怀疑）** | 任何"X 月起停推""新规死刑线""算法刚刚改了"等说法 | 99% 是博主推测，不是平台官方 | **看到先疑，要求官方公告链接**。本 skill 已删除"抖音 2026 新规<40%停推"这种主张，未来不要再加 |

**铁律**：方法论可以照搬，数字必须复核。如果你（Claude）下次诊断时发现某个阈值已经明显跟当前实战不符，告诉用户"该校准 B 档数字了"，而不是硬套旧阈值。

---

## 1. 三层诊断框架（所有平台通用骨架）

```
①漏斗自检    → 用平台专属阈值，定位卡在哪一层（曝光/点击/完播/互动）
②对标扫描    → 同赛道 5k-50k 粉账号 3-5 个，找爆款率 / 扑街率 / 选题分布
③六维拆解    → 我 vs 对标 6 维评分（定位/选题/封面/标题/正文/节奏）
```

### Layer 1：漏斗自检（卡在哪一层）

通用四指标（**平台专属阈值见 platforms/{平台}.md**）：

| 指标 | 计算 | 卡住意味着 |
|---|---|---|
| 曝光率 | 曝光 / 粉丝数 | 账号权重低 / 标签错乱 / 限流 |
| 点击率 (CTR) | 点击 / 曝光 | 封面 + 标题不及格 |
| 完播率 / 读完率 | 完播 / 点击 | 钩子 + 结构问题 |
| 互动率 | (赞+藏+评) / 曝光 | 选题没打到痛点 / 没埋互动钩子 |

**关键铁律**：阶梯流量池机制 — 任何一层跌破阈值，系统立即停推，**先定位是哪一层卡住，再去调那一层**。
不要看到不爆就先改定位，那是放弃治疗。

### Layer 2：对标扫描（同赛道在做什么）

**第一步：找候选（先攒 10-15 个，候选池要够厚）**

| 方法 | 怎么用（直接调 tikhub MCP） |
|---|---|
| 同领域博主搜索 | `xiaohongshu_app_v2_search_users` / `douyin_app_v3_fetch_user_search_result` / `kuaishou_app_search_user_v2` |
| 行业关键词搜笔记反查作者 | `xiaohongshu_app_v2_search_notes` / `douyin_app_v3_fetch_video_search_result_v2` / `kuaishou_app_search_video_v2` 按互动量倒序 |
| 平台热榜锁定头部 | `xiaohongshu_web_v2_fetch_hot_list` / `douyin_app_v3_fetch_hot_search_list` / `kuaishou_web_fetch_kuaishou_hot_list_v2` |
| 关注页 + 推荐小三角 | 看自己/已知对标账号的"相似推荐",抖音用 `douyin_xingtu_v2_get_recommend_for_star_authors` |
| 第三方数据工具 | 蝉小红 / 新红 / 灰豚数据,查赛道 top 100（人工） |
| 爆款笔记 / 话题反查 | 抖音 `_fetch_hashtag_video_list` / 小红书 `_get_topic_feed` → 按互动量倒序找重复出现的作者 |

**第二步：粉丝量匹配阶梯**（不要找比自己高 100 倍的对标 — 学不到）

| 你当前粉丝量 | 对标粉丝量区间 |
|---|---|
| 0 - 1k | 2000 - 5000 |
| 1k - 3k | 1W - 2W |
| 3k - 1W | 2W - 5W |
| 1W - 5W | 5W - 20W |
| 5W+ | 20W+ |

**第三步：三级分类**（不同级别学不同的东西）

| 级别 | 粉丝量 vs 你 | 数量 | 学什么 |
|---|---|---|---|
| **伙伴级** | 同量级或略高（×1 - ×3） | 3-5 个 | 选题 / 节奏 / 评论运营 — **可以照抄实操** |
| **榜样级** | 高 1 个数量级（×5 - ×10） | 2-3 个 | 内容结构 / 封面公式 / 人设打法 — **学方法论** |
| **大佬级** | 头部（×100+） | 1-2 个 | 战略方向 / 商业模式 / 长期节奏 — **看趋势不学动作** |

**第四步：可复制性筛选**

候选 10-15 个 → 按下面 4 条过滤 → 留 3-5 个 **可复制对标** 进 Layer 3 拆解：
- 同赛道（同人群 + 同场景）
- 近 30 天活跃发文（≥ 8 条）
- 不是蓝 V / 官方号 / MCN 大流水线（学不动）
- 没有"单笔记 100w+ 异常爆"（不可复制）

**爆款率 / 扑街率**：
```
爆款率 = 互动量 ≥ 5× 该账号平均的笔记数 / 总笔记数
扑街率 = 互动量 ≤ 0.3× 该账号平均的笔记数 / 总笔记数
```

健康账号：爆款率 ≥ 15%，扑街率 ≤ 30%。低于这个的对标，**别学**。

### Layer 3：六维拆解（我 vs 对标）

每一维 1-5 分打分（5 = 对标都做到了 + 我也做到了；1 = 对标在做我没做）：

| 维度 | 看什么（评分标准见 §5 评分术语速查） | 我得分 | 对标得分 | 差距 |
|---|---|---|---|---|
| 账号定位 | 人群 + 场景 + 价值（三位一体） | | | |
| 选题角度 | 命中赛道高频痛点 / 长尾词布局 | | | |
| 封面公式 | §5.1 五种封面命中率 | | | |
| 标题钩子 | §5.2 10 公式命中率 | | | |
| 正文骨架 | §5.3 三骨架（场景冲突 / 人设故事 / 数据对比） | | | |
| 发布节奏 | 频率 + 时段 + 矩阵化 | | | |

差距 ≥ 2 分的维度，就是**首要改进项**。

**6 维 vs "粉丝画像 / 变现模式"**：粉丝画像 和 变现模式 不进 6 维评分（避免把"结果指标"和"商业层选择"和"内容动作"混在同一张评分表里），而是走 §1.6 诊断附加项。

---

## 1.5 数据复盘优化矩阵（跨平台快查表）

> 漏斗任何一层卡住，先来这张表对一下"典型根因 + 通用修法"，再去 platforms/*.md 拿平台专属修法。
> **矩阵是急救包，平台手册是手术刀。**

| 漏斗指标卡住 | 典型根因 | 通用优化方向 | 平台专属深挖 |
|---|---|---|---|
| **3-5s 完播率低** | 开头无信息密度 / 自我介绍废话 / 首帧静止 | 切换有吸引力开头，**开头即巅峰**：把视频结尾最炸的金句/画面前置 | 抖音 §2.2 |
| **整体完播率低** | 视频时长过长 / 中段某片段突兀 / 节奏断 | 选优质片段重剪多版本测试；**卖点出现前每 3-5 秒一个钩子** | 抖音 §1.1 完播分档、快手 §2.1 |
| **25% / 50% / 75% 进度跳水** | 中间出现反感片段 / 信息密度断崖 | 看跳水时间点 → 砍掉 / 重剪那段 → 补一个反转或数据点 | 抖音 §2.2、小红书 §2.3 阅读完成率 |
| **互动率低（赞/评/藏)** | 没埋互动钩子 / 内容没"槽点" | **故意留一个槽点 / 争议点吸引评论**；结尾抛开放性问题 | 小红书 §2.3 CES、快手 §3.3 评论质量 |
| **数据好但转化率低** | 评论区没维护 / 没转化路径 | **评论必回带 @**，加引导路径（关注/私信/小程序/简介导流） | 小红书 §6 私域承接、快手 §3.3 |
| **播放时长长但转化率低** | 引入部分太长，用户走时还没看到转化点 | **缩短引入**，把转化引导前置到中段而不是结尾 | 小红书 §3 |

**用法**：先用 §1 漏斗自检定位到具体那一行 → 看通用方向心里有数 → 去对应 platforms/*.md 拿平台经验阈值 + 工具链 + 5 根因清单 → 出 P0/P1/P2 行动。

---

## 1.6 诊断附加项（不进 6 维评分，但完整诊断必查）

| 附加项 | 怎么查 | 为什么不进 6 维 |
|---|---|---|
| **粉丝画像** | 抖音：`mcp__tikhub-douyin__douyin_billboard_fetch_hot_account_fans_portrait_list`（**仅星图收录账号有数据，普通账号会空**）；小红书：靠笔记评论 + 关注列表反推；快手：API 不给，看后台 | 是**结果指标**，反映前 6 维做得对不对 — 画像与目标人群偏离 ≥ 30% = 前 6 维出问题 |
| **变现模式** | 看主页挂载（小黄车/购物车/简介引流话术） | 是**商业层选择**，不是内容诊断范畴 — 但变现链路断了，前 6 维做再好也是白干 |

**判定**：粉丝画像与目标人群偏离 ≥ 30% → 倒推查"账号定位 + 选题角度"是否飘了；变现链路缺失 → 加进 P1 行动清单（小红书必有评论区导流话术 / 抖音挂车 / 快手主页引流）。

---

## 2. 输入路由（用户给的什么形态，怎么处理）

### 输入 A：截图（笔记数据后台截图，链接可选）

```
1. 先看截图：曝光 / 点击 / 完播 / 互动 数据是否完整
2. 调 scripts/ocr_screenshot.py <截图路径>  → 拿结构化 JSON（Gemini 3.1 Pro OCR）
   {
     "platform_guess": "xiaohongshu / douyin / kuaishou / unknown",
     "metrics": {"impressions": ..., "ctr": ..., "completion": ..., ...},
     "raw_text": "OCR 全文"
   }
3. 如果用户也给了笔记链接 → 调对应平台 tikhub MCP "笔记/视频详情" 工具
   拿封面 + 标题 + 评论
4. 跳到 §4 平台专属诊断
```

### 输入 B：账号链接（自己 + 对标，可能多个对标）

```
1. 调 scripts/dispatch_account.py <account_url>  → 拿到 platform + user_id + tikhub 工具表
2. 用对应 tikhub MCP 工具，分别拿:
   - 我方：账号信息 + 最近 30 条笔记互动数据
   - 对标：账号信息 + 最近 30 条笔记互动数据
3. 计算各自的爆款率 / 扑街率 / 互动均值（Layer 2）
4. 抽样：我方 top 3 爆款 + bottom 3 扑街，对标 top 5 爆款，
   逐条调 §3 多模态分析（封面 → analyze_image，视频 → analyze_video）
5. 跳到 §4 平台专属诊断
```

### 输入 C：只给账号链接，没对标（"帮我找几个对标"）

```
1. 拿到账号信息 → 提取人群 / 赛道关键词
2. 调对应 tikhub MCP 的"关键词搜笔记"+"按互动量排序"
3. 从结果里挑 3-5 个 5k-50k 粉账号，过滤掉:
   - 蓝 V / 官方号
   - 单笔记 100w+ 异常爆（不可复制）
   - 近 30 天发文 < 8 条（不活跃）
4. 把对标候选交给用户确认 → 用户点头 → 跳到输入 B 流程
```

### 输入 D：只给一张截图，没链接没账号

```
1. ocr_screenshot.py 提数据
2. 调 §1 Layer 1 通用阈值（不用平台专属，因为不知道平台）
3. 输出"建议先告诉我平台 / 账号链接，我才能给对标差距诊断"
4. 对话补齐
```

---

## 3. 多模态分析能力（Gemini 3.1 Pro，本 skill 内置）

> 所有视觉/视频分析都走环境变量 `VIDEO_ANALYSIS_API_KEY`，对应 OpenAI 兼容协议的 Gemini 代理。
> 三个脚本统一在 `scripts/` 目录，输出严格 JSON，对齐 §5 评分术语速查。

### 3.1 截图 OCR（数据后台截图 → 结构化指标）

```
python3 ~/.claude/skills/account-diagnostic/scripts/ocr_screenshot.py <截图路径>
→ 输出 JSON：platform_guess + screenshot_type + metrics{impressions/ctr/completion/...} + raw_text + warnings
```

适用：用户截图后台数据（创作者中心、蒲公英商家后台、笔记数据页）。
**铁律**：OCR 不可信时（warnings 非空 / 关键字段为 null）必须让用户文字补齐或提供链接。

### 3.2 封面 / 首帧图分析（拿封面 5 变量 + 5 模板归类 + 钩子识别）

```
python3 ~/.claude/skills/account-diagnostic/scripts/analyze_image.py <图片路径>
→ 输出 JSON：
   cover_variables{ratio, big_text, big_text_ratio, human_presence, color_contrast, info_density}
   template_classification{matched: A/B/C/D/E, name, confidence, reason}
   hook_detection{audience_lock, benefit_promise, curiosity_gap}
   title_formula_hint{matched_formula_id: 0-10, reason}
   weakness（一句话点出 CTR 维度短板）
```

适用：拆解笔记封面（小红书）、视频首帧（抖音/快手都把首帧当封面）。
**用法**：对我方 top 3 + bottom 3 + 对标 top 5 都跑一遍，找共性模板和差距。

### 3.3 视频分析（**三种 mode**：talking / visual / keyframe + auto 自动判定）

**核心理念**：不同内容类型的视频，分析路径完全不一样。三条路径：

| Mode | 适用内容 | 分析重心 | 关键产物 |
|---|---|---|---|
| **talking** | 教程口述 / 知识科普 / 播报 / 真人说话头 | 口播稿（ASR）+ 轻量视觉分段 | `transcript_analysis`（首句钩子 / 信息密度 / CTA / 标题公式） |
| **visual** | vlog / 表演 / 美食拍摄 / 转场剪辑 | 密集分段视觉拆解（每 90s 一段） | `visual_analysis`（钩子/节奏/情绪弧）+ `key_moments` |
| **keyframe** | PPT 录屏 / 知识截图 / 思维导图 / 教程截屏 | ffmpeg 场景变化抽**关键帧** + 每帧 OCR/拆解 | `keyframe_analysis`（OCR + 知识点 + 视觉模板） |

**关键帧上限按时长动态**：≤3 分钟抽 10 张 / 3-10 分钟抽 20 张 / >10 分钟抽 30 张。

**用法**：

```
# 默认 auto 模式：抽 5 张代表帧 + 前 30s 音轨喂 Gemini 自动判定 content_type
python3 ~/.claude/skills/account-diagnostic/scripts/analyze_video.py <视频路径>

# 强制走某条路径（已知内容类型时省一次判定调用）
python3 ~/.claude/skills/account-diagnostic/scripts/analyze_video.py <视频路径> --mode talking
python3 ~/.claude/skills/account-diagnostic/scripts/analyze_video.py <视频路径> --mode visual
python3 ~/.claude/skills/account-diagnostic/scripts/analyze_video.py <视频路径> --mode keyframe
```

**输出 JSON 公共字段**：`video_path / duration_seconds / mode_requested / mode_used / mode_detection`（auto 模式额外有）。
**模式专属字段**：见上表"关键产物"列。

**铁律**（澄清旧"绝不抽帧"）：
- **不抽时序帧**：visual 模式下钩子/节奏/情绪弧是时序信息，均匀抽帧会丢光 → 走分段视频片段
- **必须抽场景帧**：keyframe 模式下画面是稳定文字载体（PPT / 截图），时序信息少 → ffmpeg `select='gt(scene,0.3)'` 抽场景变化关键帧 → 每帧单独 OCR + 拆知识点
- **talking 模式 ASR 必须跑通**：没设 `AUDIO_TRANSCRIPTION_API_KEY` 直接报错退出（口播主导视频没 ASR = 没法分析）

**用法建议**：
- 抖音 / 快手的"完播率有问题"的视频 → auto 一般会判 visual，重点看前 5s 钩子
- 小红书的"教程类长图文视频" → auto 一般会判 keyframe，重点看每张关键帧的 OCR + 信息密度
- 知识口播号 / 播客切片 → auto 一般会判 talking，重点看首句口播 + CTA

### 3.4 评论拉取 + 痛点聚类（文本分析，不走 Gemini，但走 LLM 推理）

```
1. 用 tikhub MCP 拉评论：
   - 抖音：mcp__tikhub-douyin__douyin_app_v3_fetch_video_comments
   - 小红书：mcp__tikhub-xiaohongshu__xiaohongshu_web_v2_fetch_note_comments
   - 快手：mcp__tikhub-kuaishou__kuaishou_app_fetch_one_video_comment
2. 取前 50-100 条评论，让 Claude 做痛点聚类 + 情绪分布
3. 输出：top 5 高频痛点 + 评论情绪分布（正/负/求资源/吐槽）
```

适用：判断"内容打到痛点了吗"，对标爆款必跑（看观众真实反馈，不只看赞数）。

### 3.5 媒体下载小贴士

```
# 抖音视频高画质播放地址
mcp__tikhub-douyin__douyin_app_v3_fetch_video_high_quality_play_url(aweme_id=...)
→ 拿到 URL 后用 curl/wget 下载到 /tmp/account_diag/{aweme_id}/video.mp4

# 小红书笔记图片
mcp__tikhub-xiaohongshu__xiaohongshu_web_v2_fetch_note_image(note_id=...)
→ 拿到图 URL 列表

# 快手视频
mcp__tikhub-kuaishou__kuaishou_app_fetch_one_video(photo_id=...)
→ 拿到 play_url
```

---

## 4. 平台专属诊断（每个平台 2 大主逻辑）

> **每个平台都有自己的子手册**，里面有：阈值表、工具映射、6 维评分细则、行动建议清单。
> Claude 读完本节先跳到对应 platforms/*.md 加载平台细节，再继续报告。

| 平台 | 子手册 | 主逻辑 1 | 主逻辑 2 |
|---|---|---|---|
| 抖音 | [platforms/douyin.md](platforms/douyin.md) | **5s完播率诊断**（行业合格线 ~50%） | **钩子诊断**（前 3 帧 + 首句口播） |
| 小红书 | [platforms/xiaohongshu.md](platforms/xiaohongshu.md) | **CES + 封面 CTR 诊断** | **搜索分发诊断**（近 70% 月活有搜索行为） |
| 快手 | [platforms/kuaishou.md](platforms/kuaishou.md) | **完播 + 关注转化率诊断**（老铁经济） | **同城分发 + 评论质量诊断** |

**⚠️ 阈值数据来源声明**：本 skill 所有平台阈值（完播率/CTR/CES/互动率等）均为 **行业经验值**（来自蝉妈妈/千瓜/新红/新浪财经 COO 公开演讲等多源），**非平台官方公告**。具体出处见各 platforms/*.md 顶部的"数据来源"小节。诊断时用作"方向判断"，不是"绝对死线"。

---

## 5. 评分术语速查（自包含 — 6 维评分都对齐这套）

> 这一节是本 skill 的"内置词典"，所有平台手册的"封面公式 / 标题钩子 / 正文骨架 / 视频钩子"都引这里。
> 没有这一节，6 维评分就没共同语言。

### 5.1 五种封面模板（A/B/C/D/E）

| 编号 | 名称 | 特征 | 典型场景 |
|---|---|---|---|
| **A** | 大字报型 | 整张图 50%+ 是大字标语，颜色高对比 | 教程 / 干货 / 避坑（小红书最常见） |
| **B** | 对比型 | Before/After 左右或上下分屏，箭头/对勾突出差异 | 减肥 / 美妆 / 装修 / 改造 |
| **C** | 真人出镜型 | 真人脸 + 表情夸张 + 大字配文 | 吃播 / 测评 / 故事号 |
| **D** | 实物展示型 | 产品/物品居中，无人或仅手出镜，干净背景 | 好物推荐 / 商品种草 / 工具展示 |
| **E** | 表格截图型 | 文字密集，表格/清单/聊天截图直接当封面 | 资源贴 / 攻略 / 数据对比 |

**评分**：5 分 = 命中模板 + 大字 ≥ 1/4 + 高对比 + 人群锚定；1 分 = 随便截一张 / 无字 / 同色系。

### 5.2 10 个标题公式

| 编号 | 名称 | 模板 | 例子 |
|---|---|---|---|
| 1 | 数字+人群+效果 | 「N 个 [动作]，[人群] [效果]」 | "3 个动作，新手妈妈 1 小时哄睡" |
| 2 | 反认知钩子 | 「原来 [认知反例]」 | "原来卸妆油才是闷痘元凶" |
| 3 | 极端体验 | 「[极端形容词] + [对象]」 | "一辈子只用这一支防晒" |
| 4 | 怕错避坑 | 「千万别 [行为]，否则 [后果]」 | "千万别空腹喝美式，胃要烂" |
| 5 | 答案前置 | 「[问题] 答案是 [反差答案]」 | "脸黄到底是什么原因？不是肝" |
| 6 | 身份共鸣 | 「我是 [身份]，我 [行为/选择]」 | "我是 985 学姐，我从不背单词" |
| 7 | 升维加码 | 「不是 [常规]，是 [升级版]」 | "不是减肥餐，是不易胖的代谢餐" |
| 8 | 资源诱饵 | 「[数字] 份 [资源]，[条件领取]」 | "100 份小红书选题表，评论扣 1" |
| 9 | 时间锚定 | 「[时长] 学会 / 改变 [事]」 | "30 天，从 1k 到 1W 粉" |
| 10 | 对比反差 | 「[A] vs [B]，差别 [惊人结果]」 | "学渣 vs 学霸笔记，差的不是字" |

**评分**：5 分 = 命中 1 个明确公式 + 数字/人群/利益齐全；1 分 = 平铺直叙 / 无钩子。

### 5.3 三种正文骨架

| 编号 | 名称 | 结构 | 适用 |
|---|---|---|---|
| **A** | 场景+冲突+解决 | 设场景 → 抛冲突/痛点 → 给解决方案 → 升华/CTA | 教程类 / 痛点解决 |
| **B** | 人设+故事+产品 | 立人设 → 讲个人故事 → 自然带出产品/方法 → 邀请互动 | 故事号 / 种草 |
| **C** | 数据对比+结论 | 摆数据/对比 → 分析差异 → 给结论 → 转化引导 | 评测 / 攻略 / 干货 |

**评分**：5 分 = 命中骨架 + 首句钩子 + 中段不塌 + 结尾有 CTA；1 分 = 流水账 / 无结构。

### 5.4 七种视频开头钩子（前 3-5 秒）

| 编号 | 名称 | 模板 | 例子（首句口播） |
|---|---|---|---|
| 1 | 提问钩 | 「你是不是也 [痛点]？」 | "你是不是也吃完就困？" |
| 2 | 反差钩 | 「以为 [常识]，其实 [反例]」 | "都说蛋白粉伤肾，错了" |
| 3 | 数字钩 | 「[数字] + [利益/效果]」 | "3 招让你的简历过 BOSS 直聘" |
| 4 | 承诺钩 | 「看完这条视频，你就能 [结果]」 | "1 分钟教会你拍出大片" |
| 5 | 悬念前置 | 直接放结尾最炸的一帧/金句，倒叙开始 | "（前/后对比图）这是怎么做到的？往下看" |
| 6 | 身份锁定 | 「如果你是 [人群]，这条必看」 | "30+ 女性，这 5 个补剂别吃错" |
| 7 | 利他诱饵 | 「我帮你做完了 [事]，免费拿」 | "我整理了 200 个小红书选题，评论扣 1" |

**评分**：5 分 = 前 3 帧 = 利益+人群+好奇三合一 + 首句口播命中公式 + 封面/首帧一致；1 分 = "大家好今天给大家分享" / 静止画面 / 无钩子。

---

## 6. 抓取深度决策（自动决定分析多少条）

不要"全抓全分析"，token 浪费。按账号体量分档：

| 账号笔记总数 | 我方笔记抓取 | 对标账号抓取（每个） | Gemini 多模态深度拆解条数 |
|---|---|---|---|
| < 50 | 全部 | 全部 | 我方 top 3 + bottom 3，对标 top 3 |
| 50 - 200 | 最近 30 + 历史 top 10 | 最近 30 + top 5 | 我方 top 3 + bottom 3，对标 top 5 |
| 200 - 500 | 最近 30 + top 10 + bottom 10 | 最近 30 | 我方 top 3 + bottom 3，对标 top 5 |
| > 500 | 最近 30 + top 10 + bottom 10 | 最近 30 | 我方 top 5 + bottom 5，对标 top 5 |

**单次诊断 Gemini 多模态深度拆解上限：15 条**。再多就分批，给用户阶段性报告。

---

## 7. 输出格式（严格按这个模板）

```markdown
# 账号诊断报告 — @[账号名]

## 0. TL;DR（先给结论）
- **卡在哪一层**：曝光 / 点击 / 完播 / 互动（命中其中 1-2 层）
- **首要改进项**：6 维里差距 ≥ 2 分的维度（按差距倒序）
- **本周行动 3 件事**：具体到"改封面成 X 模板 / 标题套 N 号公式 / 加一句首句钩子"

## 1. 账号体检（漏斗自检）
| 指标 | 我的实际值 | 平台阈值 | 判定 |
|---|---|---|---|
| 曝光率 | | | ✅ / ⚠️ / ❌ |
| CTR | | | |
| 完播率 / 读完率 | | | |
| 互动率 | | | |

→ **结论**：卡在 X 层。原因初判：…

## 2. 对标扫描

### 2.1 候选概览（带级别）
| 对标账号 | 粉丝数 | 级别（伙伴/榜样/大佬） | 近 30 天爆款率 | 扑街率 | 高频选题 | 主用封面模板 |
|---|---|---|---|---|---|---|
| @A | | 伙伴 | | | | |
| @B | | 榜样 | | | | |
| @C | | 大佬 | | | | |

### 2.2 深度拆解矩阵（维度 × 对标）
| 维度 | 对标 A（伙伴） | 对标 B（榜样） | 对标 C（大佬） | 我方现状 |
|---|---|---|---|---|
| 账号定位（人群+场景+价值） | | | | |
| 选题角度（高频痛点 / 长尾词） | | | | |
| 笔记封面公式 | | | | |
| 标题钩子公式 | | | | |
| 开头钩子 / 结尾设计 | | | | |
| 粉丝画像（推测 or 实测） | | | | |
| 变现模式（挂载 / 私域 / 直播） | | | | |
| **可借鉴 3 条**（具体动作） | 1.…  2.…  3.… | 1.…  2.…  3.… | 1.…  2.…  3.… | — |

→ **结论**：赛道在做什么 X、Y、Z；我没在做的是 W。
→ **可抄清单**：从伙伴抄动作 N 条；从榜样学方法 M 条；从大佬看趋势 L 条。

## 3. 六维拆解（我 vs 对标平均）
| 维度 | 我 | 对标平均 | 差距 | 短板诊断 |
|---|---|---|---|---|
| 账号定位 | | | | |
| 选题角度 | | | | |
| 封面公式 | | | | |
| 标题钩子 | | | | |
| 正文骨架 | | | | |
| 发布节奏 | | | | |

## 4. 平台专属诊断（按 platforms/*.md 套用）
**主逻辑 1：[平台主指标] 诊断**
- 我的实际值：…
- 阈值：…
- 判定 + 根因：…

**主逻辑 2：[平台第二主逻辑] 诊断**
- …

## 5. 单条深度拆解（Gemini 多模态报告摘要）
### 我方 top 1：[标题]
- 命中模板：封面 X / 标题 N 号 / 骨架 Y / 钩子 Z
- 评论质量：✅ 有效爆 / ❌ 无效爆
- 可复用元素：…

### 我方 bottom 1：[标题]
- 短板：…
- 对照对标 top X，差在 …

### 对标 top 1：[标题]
- 可抄什么：…

## 6. 行动清单（优先级排序）
**P0（本周改）**
1. ……

**P1（本月调）**
1. ……

**P2（季度沉淀）**
1. ……

## 7. 30 / 60 / 90 验证指标
- 30 天：曝光率提升 X% / 完播率达到 Y%
- 60 天：单月爆款 ≥ N 条
- 90 天：粉丝从 a 到 b
```

---

## 8. tikhub MCP 工具速查（按平台 × 任务）

> 三大平台都有完整 tikhub MCP，本 skill 全部直接调用，不依赖任何其他 search skill。

### 抖音（mcp__tikhub-douyin__）
| 任务 | 工具 | 关键参数 |
|---|---|---|
| 账号信息 | `douyin_web_handler_user_profile` (基本) / `_v4`（带性别+直播等级） | `sec_user_id` |
| 用户作品列表 | `douyin_web_fetch_user_post_videos` | `sec_user_id` + `count` |
| 视频详情 | `douyin_app_v3_fetch_one_video` | `aweme_id` |
| 视频统计（播放/赞/转/下） | `douyin_app_v3_fetch_video_statistics` | `aweme_ids` |
| 视频高画质播放 URL | `douyin_app_v3_fetch_video_high_quality_play_url` | `aweme_id` 或 `share_url` |
| 视频评论 | `douyin_app_v3_fetch_video_comments` | `aweme_id` |
| 关键词搜作者（找对标） | `douyin_app_v3_fetch_user_search_result` | `keyword` |
| 关键词搜视频（找选题） | `douyin_app_v3_fetch_video_search_result_v2` | `keyword` |
| 短链解析（v.douyin.com） | `douyin_app_v3_fetch_one_video_by_share_url` | `share_url` |
| 粉丝画像（深度诊断） | `douyin_billboard_fetch_hot_account_fans_portrait_list`（仅星图收录账号有数据，普通账号会空） | `sec_uid` |
| 热搜榜 | `douyin_app_v3_fetch_hot_search_list` | — |

### 小红书（mcp__tikhub-xiaohongshu__）
| 任务 | 工具 | 关键参数 |
|---|---|---|
| 账号信息 | `xiaohongshu_app_v2_get_user_info` / `xiaohongshu_web_v2_fetch_user_info` | `user_id` |
| 用户笔记列表 | `xiaohongshu_app_v2_get_user_posted_notes` | `user_id` + `cursor` |
| 笔记详情 | `xiaohongshu_web_v2_fetch_feed_notes_v2` | `note_id` |
| 笔记图片 | `xiaohongshu_web_v2_fetch_note_image` | `note_id` |
| 笔记评论 | `xiaohongshu_web_v2_fetch_note_comments` | `note_id` + `cursor` |
| 评论子回复 | `xiaohongshu_web_v2_fetch_sub_comments` | `note_id` + `comment_id` |
| 关键词搜笔记 | `xiaohongshu_app_v2_search_notes` | `keyword` + `sort_type` |
| 关键词搜用户 | `xiaohongshu_app_v2_search_users` | `keyword` |
| 热榜 | `xiaohongshu_web_v2_fetch_hot_list` | — |
| 话题信息 + 笔记 | `xiaohongshu_app_v2_get_topic_info` + `_get_topic_feed` | `page_id` |
| 分享链接解析 | `xiaohongshu_app_get_user_id_and_xsec_token` / `xiaohongshu_web_get_note_id_and_xsec_token` | `share_link` |

### 快手（mcp__tikhub-kuaishou__）
| 任务 | 工具 | 关键参数 |
|---|---|---|
| 账号信息 | `kuaishou_app_fetch_one_user_v2` / `kuaishou_web_fetch_user_info` | `user_id` |
| 用户作品列表 | `kuaishou_app_fetch_user_post_v2` | `user_id` + `pcursor` |
| 用户热门作品 | `kuaishou_app_fetch_user_hot_post` | `user_id` |
| 视频详情 | `kuaishou_app_fetch_one_video` | `photo_id` |
| 视频评论 | `kuaishou_app_fetch_one_video_comment` | `photo_id` |
| 用户直播信息 | `kuaishou_app_fetch_user_live_info` | `user_id` |
| 关键词搜视频 | `kuaishou_app_search_video_v2` | `keyword` + `page` |
| 关键词搜用户 | `kuaishou_app_search_user_v2` | `keyword` + `page` |
| 综合搜索 | `kuaishou_app_search_comprehensive` | `keyword` |
| 热榜 | `kuaishou_web_fetch_kuaishou_hot_list_v2` | `board_type=1` |
| 分享链接解析 | `kuaishou_web_fetch_one_video_by_url` / `kuaishou_web_fetch_get_user_id` | `url` / `share_link` |

### 本地脚本（scripts/）
| 任务 | 工具 |
|---|---|
| 截图 → 数据 | `scripts/ocr_screenshot.py <截图路径>` |
| 链接 → 平台+ID | `scripts/dispatch_account.py <账号URL>` |
| 封面/首帧 → 5 变量+模板 | `scripts/analyze_image.py <图片路径>` |
| 视频 → 分段拆解+转写 | `scripts/analyze_video.py <视频路径>` |

---

## 9. 关键铁律（必读）

1. **先定位漏斗层，再谈改什么**。看到不爆就先改定位 = 放弃治疗。
2. **对标必须 5k-50k 粉，同赛道，活跃**。学不到的对标不是好对标。
3. **6 维评分要给数字（1-5）**，别说"还可以 / 一般"。差距 ≥ 2 才动。
4. **平台阈值是经验值，不是官方死刑线**。所有数字都是蝉妈妈/千瓜/新红等行业拆解的中位数（见 platforms/*.md 顶部"数据来源"），用作方向判断，**不要写"低于 X 必死"这种绝对话**，会误导用户。
5. **截图 OCR 不可信时强制要求链接**。后台截图字段经常糊 / 截不全 / 不同后台版本字段不一样。
6. **不分析"为什么对方爆"**（那是单条拆解的活），**只分析"我和对方差在哪"**。
7. **抓取深度按 §6 表执行**，单次拆解上限 15 条。token 不是免费的。
8. **行动清单按 P0 / P1 / P2 排**，给用户清楚的优先级，不要给一串平等的建议。
9. **找对标候选要 10-15 个，留 3-5 个"可复制对标"**。三级分类（伙伴/榜样/大佬）各有所学：伙伴学动作、榜样学方法、大佬看趋势 — 别全学伙伴，也别全学大佬。
10. **数据卡住先查 §1.5 优化矩阵，再去 platforms/*.md 拿平台修法**。矩阵是急救包，平台手册是手术刀，顺序别反。
11. **视频分析按 mode 路由**（见 §3.3）：talking 看口播稿、visual 走分段视频、keyframe 抽场景关键帧。auto 模式自动判定。**绝不对时序内容做均匀抽帧**（钩子/节奏/情绪弧会被抽帧丢光），但**图文密集类必须抽场景关键帧**（PPT / 知识截图画面是稳定文字载体）— 两者不矛盾。
12. **评分术语全部用 §5 速查表**。别自己造词，否则 6 维评分和对标对不上。
