# 抖音账号 / 内容诊断子手册

> 主 skill：`social-account-doctor`。本手册被 §3 平台专属诊断章节调用。
> **核心特性**：完播率（特别是 5s 完播率）是抖音冷启动的核心权重之一。**注意**：抖音从未公开过"低于 X% 停推"的硬阈值，本手册所有数字都是行业经验值（蝉妈妈/知乎多源），用作方向判断而非绝对死线。

---

## 0. 数据来源声明

本手册阈值均为**行业经验值**（非平台官方），主要来源：

- 蝉妈妈数据 — [完播率话题](https://www.chanmama.com/yunyingquan/topic/3126.html) / [核心数据指标](https://www.chanmama.com/yunyingquan/question/4274.html) / [完播率多少算正常](https://www.chanmama.com/yunyingquan/question/4338.html)
- 知乎运营拆解 — [5s完播率定义](https://zhuanlan.zhihu.com/p/608114574) / [完播率视频时长](https://zhuanlan.zhihu.com/p/690186906) / [运营关键指标](https://zhuanlan.zhihu.com/p/411261710) / [2025 抖音算法首次公开](https://zhuanlan.zhihu.com/p/1897014736534631373)
- 鸟哥笔记 — [比起完播率更重要的指标](https://www.niaogebiji.com/article-31701-1.html)
- 巨量算数 — [trendinsight.oceanengine.com](https://trendinsight.oceanengine.com/)（官方但未公开账号诊断阈值表）

⚠️ **网传"2026 新规 5s完播<40%自动停推"在所有可查源中均无官方背书**，本手册按"经验合格线 50%"处理。

📅 **数据采集日期：2026-04 / 建议复核周期：6 个月**。抖音算法每年迭代 2-3 次（特别是完播率分档与互动权重），过期数字会误导诊断。复核方法：用上述来源重跑一遍，对比偏移 > 20% 就更新阈值表。

---

## 0.5 算法规则速查 — T0/T1（可执行版）

> ⭐ **算法核心信号 = 完播率（5s 完播 → 全程完播）**。差距 ≥ 1 档时**优先于其他维度修** — 抖音冷启动池子能不能跑出去全靠 5s 完播，其他维度没及格也救不回来。
>
> T0 = 不做就死；T1 = 不做次推。

| 级 | 规则 | 怎么做（动作） | 不做的代价 |
|---|---|---|---|
| ⭐ **T0** | 首帧（0:00-0:01）放结果画面或最炸的一帧 | 倒叙结构：把视频结尾最炸的金句 / 画面前置到第 0 秒 | 5s 完播 < 40%，冷启动池出不去 |
| ⭐ **T0** | 首句口播禁用"大家好 / 今天给大家" | 砍前 1.5 秒废话，首句直接钩子（提问 / 承诺 / 反差 / 数字之一，套 §5.4 七模板） | 5s 完播 -20%，进不到下一流量池 |
| ⭐ **T0** | 视频时长 ≤ 30 秒（新手期） | 跑通 30s 完播 ≥ 35% 再加长 | 完播天然偏低，被算法判定低质 |
| **T1** | 黄金 7 秒密度点（每 7 秒 1 个反转 / 数据 / 画面切） | 中段禁止 ≥ 5s 静止镜头或重复 | 25% / 50% / 75% 进度位看到完播跳水 |
| **T1** | 首帧 = 封面（不是描述区那张图） | 把"大字 + 利益承诺"做进 0:00 视频帧本身 | 信息流不点开 = CTR < 3% |
| **T1** | 稳定日更，≥ 3 条/周 + 固定时段 | 早 7-9 / 中 12-13 / 晚 19-22 三选一固定 | 标签衰减，账号权重下降 |
| **T1** | 优化顺序：完播 > 互动 > 关注 | 先调首帧 / 首句（完播）→ 再调互动钩子 → 最后调人设；顺序不能反 | 投入产出比差 10 倍 |

---

## 1. 阈值表（行业经验值，非官方）

| 指标 | 计算 | 偏低 | 合格 | 优秀 | 卡住意味着 |
|---|---|---|---|---|---|
| 曝光率 | 24h 曝光 / 粉丝数 | < 0.3 | 0.3-1.0 | > 1.0 | 限流 / 标签错乱 / 账号权重低 |
| 点击率 (CTR) | 点击 / 曝光 | < 3% | 3-6% | > 8% | 封面 + 标题不及格 |
| **5s完播率** | **看到 5s 的人数 / 点击数** | **< 40%** | **40-55%** | **> 55%** | **钩子崩了，前 3 帧或首句口播没抓住** |
| 完播率（按时长分档） | 完整看完 / 点击 | 见 §1.1 | | | 节奏断了 / 中段无信息密度点 |
| 互动率 | (赞+评+藏+转) / 曝光 | < 1% | 1-3% | > 3-5% | 选题没共鸣 / 没埋互动钩子 |
| 关注转化率 | 新增关注 / 曝光 | < 0.05% | 0.1-0.3% | > 0.3% | 人设模糊 / 无复购理由 |
| 2跳率 | 看了第二条 / 看了第一条的同账号粉丝 | < 5% | 5-15% | > 15% | （注：此指标定义和阈值在公开源中无统一标准，仅供参考） |

### 1.1 完播率分档阈值（经验值，非官方）

| 视频时长 | 偏低 | 合格 | 优秀 |
|---|---|---|---|
| ≤ 30 秒 | < 35% | 35-55% | > 55% |
| 30 - 60 秒 | < 20% | 20-35% | > 35% |
| 60 - 180 秒 | < 12% | 12-25% | > 25% |
| > 180 秒 | < 8% | 8-15% | > 15% |

**经验铁律**：抖音算法对完播率的权重确实高，**视频越长越拼"留住人的能力"**。新手默认 ≤ 30 秒，跑通完播再加长。具体阈值因品类波动较大（剧情类天然完播低，干货类天然完播高），用区间不要用绝对值。

---

## 2. 主逻辑 1：5s完播率诊断（行业普遍认为是头号关注指标）

### 2.1 怎么定位是不是卡在这一层

```
1. 漏斗看到 5s完播率 < 40-50% → 直接进本节
2. 调 tikhub douyin douyin_app_v3_fetch_one_video(aweme_id)
   → 拿 video_url + cover_url + 完播率 + 5s留存
3. 把 video_url 下载到 /tmp/account_diagnostic/{aweme_id}/video.mp4
4. 调 scripts/analyze_video.py（分段裁剪喂 Gemini，**不走抽帧**）
   → 拿前 5s 的画面变化、口播文字、信息密度点分布
5. 对照 §2.2 五种钩子失败模式定位根因
```

### 2.2 5s完播率崩盘的五种典型根因

| 根因 | 现象 | 修法 |
|---|---|---|
| **首帧无信息** | 黑屏 / 慢推镜头 / 平台 logo 占满 3 秒 | 首帧直接放结果画面（前/后对比，最炸的一帧） |
| **首句口播废话** | "大家好今天我来给大家分享…" | 首句必须是钩子句，砍掉自我介绍 |
| **画面静止** | 5 秒内只有一个固定镜头 | 每 1.5 秒切一个画面（叠字/缩放/转场） |
| **信息密度低** | 前 5 秒没给到任何"利益承诺" | 把视频结尾的"金句"前置到第 1 秒，倒叙结构 |
| **目标人群不清** | 通用开头，谁都能看，谁都不留 | 首句锁人群："如果你是 [人群]，看完能省 [数字]" |

### 2.3 工具调用链（5s完播率诊断专用）

```
tikhub douyin douyin_web_fetch_user_post_videos(sec_user_id, count=30)
  → 拿最近 30 条 aweme_id

# 取 top 3 完播率最高 + bottom 3 完播率最低
tikhub douyin douyin_app_v3_fetch_one_video(aweme_id)
  → 拿单条数据 + 媒体 URL

# 下载视频前 10s
ffmpeg -i video.mp4 -t 10 -c copy /tmp/.../prefix.mp4

# 让 Gemini 拆前 5s
python3 ~/.claude/skills/social-account-doctor/scripts/analyze_video.py prefix.mp4
  → 输出：首帧描述 / 口播 ASR / 画面切换次数 / 信息密度点位

# 对比 top vs bottom：差距在哪
```

---

## 3. 主逻辑 2：钩子诊断（前 3 帧 + 首句口播）

### 3.1 钩子诊断三件套

| 维度 | 拆什么 | 工具 |
|---|---|---|
| **前 3 帧画面** | 是否锁人群？是否给利益？是否制造好奇？ | scripts/analyze_image.py（截 0s/1s/2s 三帧） |
| **首句口播** | SKILL.md §5.4 七大钩子模板命中哪种？ | analyze_video.py 拿 ASR 文本 → 套公式比对 |
| **封面 vs 视频首帧一致性** | 封面承诺的 X，视频首帧给到了吗？ | 同时跑两个 analyze_image，对比 big_text 字段 |

### 3.2 钩子打分细则（1-5 分）

| 分数 | 描述 |
|---|---|
| 5 | 前 3 帧 = 利益+人群+好奇三合一；首句口播命中 SKILL.md §5.4 七大钩子公式；封面/首帧一致 |
| 4 | 三项命中两项 |
| 3 | 三项命中一项 |
| 2 | 有意识做钩子但执行差（比如有口播钩子但首帧黑屏） |
| 1 | 完全无钩子（自我介绍开头 / 静止画面 / 封面与视频脱节） |

**差距 ≥ 2 分** 时，钩子直接进 P0 行动清单。

---

## 4. tikhub-douyin 工具映射表

> 首选 / Fallback。首选挂时按列依次重试。

| 任务 | 首选 | Fallback |
|---|---|---|
| 账号信息（昵称/粉丝/认证） | `douyin_web_handler_user_profile` | `douyin_app_v3_handler_user_profile` → `douyin_web_handler_user_profile_v4`（带性别+直播等级） |
| 账号粉丝/关注关系 | `douyin_web_fetch_user_relation_stat` (无此工具时) → `douyin_web_fetch_user_following_list` | `douyin_app_v3_fetch_user_following_list` |
| 用户作品列表 | `douyin_web_fetch_user_post_videos` | `douyin_app_v3_fetch_user_post_videos` |
| 用户喜欢列表（看口味） | `douyin_web_fetch_user_like_videos` | `douyin_app_v3_fetch_user_like_videos` |
| 视频详情 | `douyin_app_v3_fetch_one_video` | `douyin_app_v3_fetch_one_video_v2` → `_v3` → `douyin_web_fetch_one_video` |
| 视频统计（播放/点赞/转发/下载） | `douyin_app_v3_fetch_video_statistics` | `douyin_app_v3_fetch_multi_video_statistics`（批量） |
| 视频高画质播放地址 | `douyin_app_v3_fetch_video_high_quality_play_url` | `douyin_web_fetch_video_high_quality_play_url` |
| 视频评论 | `douyin_app_v3_fetch_video_comments` | `douyin_web_fetch_video_comments` |
| 关键词搜索作者（找对标） | `douyin_app_v3_fetch_user_search_result` | `douyin_web_fetch_user_search_result_v3` |
| 关键词搜索视频（找选题/对标作品） | `douyin_app_v3_fetch_video_search_result_v2` | `douyin_app_v3_fetch_general_search_result` |
| 短链解析（v.douyin.com） | `douyin_app_v3_fetch_one_video_by_share_url` | `douyin_app_v3_fetch_share_info_by_share_code` |
| 创作者中心粉丝画像（深度诊断） | `douyin_billboard_fetch_hot_account_fans_portrait_list`（**仅星图收录账号有数据，普通账号会返回空**） | `douyin_billboard_fetch_hot_account_fans_interest_topic_list` |

### 4.1 推荐调用顺序（输入 = 账号链接时）

```
1. dispatch_account.py <url> → 拿到 sec_user_id
2. douyin_web_handler_user_profile(sec_user_id) → 账号基础信息
3. douyin_web_fetch_user_post_videos(sec_user_id, count=30) → 最近 30 条 aweme_id 列表
4. 计算每条互动数据（avg_play, avg_like, avg_comment）→ 算爆款率/扑街率
5. 取 top 3 + bottom 3 → 对每条调 douyin_app_v3_fetch_one_video → 拿完整指标
6. 对 top 3 + bottom 3 → analyze_video.py 拆前 5s 钩子
7. 关键词搜索 → 找对标候选（5k-50k 粉，活跃，同赛道）
```

---

## 5. 抖音版六维评分细则

| 维度 | 抖音特化指引 |
|---|---|
| **账号定位** | 看主页 9 宫格风格统一性 + 简介人群锁定 + 前 5 条视频是否同主题 |
| **选题角度** | 是否命中赛道高频词（用 `douyin_app_v3_fetch_video_search_result` 验证）+ 长尾差异化 |
| **封面公式** | **抖音的"封面"是动态首帧，不是静态大字报**。看首帧是否高反差 / 大字 / 真人锚点 |
| **标题钩子** | 抖音标题（描述）作用低于小红书，但仍要套 SKILL.md §5.2 10 个标题公式（数字+人群+效果） |
| **正文骨架** | **前 3 秒口播 + 黄金 7 秒密度点**（每 7 秒一个反转/数据/画面切）。MrBeast 公式 |
| **发布节奏** | 抖音算法偏爱"稳定日更"。频率 < 3 条/周 → 标签衰减 |

---

## 6. 行动建议清单（按 P0/P1/P2 排）

### P0（本周必须改 — 直接卡漏斗的项）

- [ ] **如果 5s完播率 < 40%**：把首帧换成"结果画面"（最炸的一帧前置），首句口播改成钩子句
- [ ] **如果 完播率 跌出分档合格区间**：砍视频时长到 ≤ 30 秒，跑通再加
- [ ] **如果 2跳率 > 15%**：第二条视频明显不吸引同账号粉丝，**全账号选题对齐 top 1 风格**
- [ ] **如果 CTR < 3%**：换封面（首帧），用 scripts/analyze_image.py 跑 top 3 对标的封面 5 变量

### P1（本月调 — 系统性短板）

- [ ] 钩子六维评分 ≤ 2 → 强制套 SKILL.md §5.4 七公式，每条视频一个
- [ ] 选题维度差距 ≥ 2 → 用 `douyin_app_v3_fetch_video_search_result` 扫赛道 top 50，提炼 10 个共性选题模板
- [ ] 评论互动率 < 1% → 视频结尾埋问题钩子（"你们怎么看？评论区扣 1"）

### P2（季度沉淀）

- [ ] 矩阵化：主号 + 2-3 个垂直子号（不同人设/不同细分赛道，互导粉丝）
- [ ] 粉丝画像验证：调 `douyin_billboard_fetch_hot_account_fans_portrait_list`（**注意：仅星图收录账号有数据，普通账号无法用此 API，需要用户提供后台截图代替**），看实际粉丝是否=目标人群
- [ ] 2跳率持续 > 15% → 重新审视账号定位（人群+场景+价值三位一体）

---

## 7. 关键铁律（抖音专属）

1. **5s完播率是冷启动核心权重之一**。多源经验值合格线 ~50%，<40% 视为偏低需重点优化。**注意**：网传"<40% 自动停推"无官方背书，不要当真理。
2. **完播率比互动率重要**。点赞高但完播低，下条照样不推。
3. **视频越长，合格线越低，但天花板更高**。新手 ≤ 30 秒，进阶 30-60 秒，人设号 60s+。
4. **首帧是封面**。不要在描述区写"封面失败"，封面就是 0:00 那一帧。
5. **不要用"大家好"开头**。直接砍掉前 1.5 秒的废话。
6. **2跳率指标定义在业界没有统一标准**，本手册仅作辅助参考；首选指标永远是完播率 + 关注转化率。
