# mediacrawler/ — 用自己账号登录的数据源（免 TikHub key）

> 对接 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)（Playwright 真实浏览器爬虫）。
> 没有 TikHub API key 时，用**自己的小红书 / 抖音 / 快手 / B 站账号**扫码登录，就能跑 find / crack / 账号诊断的数据获取。

## 它解决什么

| | TikHub 路径 | MediaCrawler 路径（本目录） |
|---|---|---|
| 需要什么 | TikHub API key（按调用付费） | 只需自己平台账号，扫码一次 |
| 原理 | 云端 REST API | 本机 Playwright 浏览器，带登录态请求 |
| 覆盖平台 | 五平台（含视频号） | 小红书 / 抖音 / 快手 / B 站（**无视频号**） |
| 稳定性 | 平台接口有版本波动 | 受登录风控影响，适合小批量（几十条/次） |
| 成本 | 计费 | 免费 |

两条路径输出同一套分析链路（find/crack/adapt 不变），按环境自检结果选择：`TIKHUB_API_KEY` 没配或用户明确不想用 → 走本路径。

## 安装（一次性）

```bash
mc --setup          # 或 python3 mediacrawler/bin/mc --setup
```

做五件事（全部落在 `vendor/`，已在 `.gitignore`）：
1. 克隆 MediaCrawler 到 `vendor/MediaCrawler`（优先 pin 到适配过的 commit；github 直连失败自动回退 gh 代理镜像）
2. 用系统 Python ≥ 3.10 建独立 venv `vendor/mc-venv`（不污染主环境）
3. 安装依赖 —— 优先装裁剪版 `requirements-lean.txt`（砍掉 webui/测试/迁移类包，省下载），自检不过自动回退上游全量 requirements
4. 安装 Playwright chromium（约 200MB；官方 CDN 明显更慢时自动切 npmmirror 镜像）
5. 把 `ENABLE_CDP_MODE` 补丁为 `False`（走标准 Playwright 模式，登录态可持久化）

所有下载源（pip / Chromium / git）在安装时**自动探测选最快**——国内裸连 GitHub/PyPI/Playwright CDN 常常只有几十 KB/s，镜像源能快一到两个数量级。用户环境变量永远优先，也可强制指定：

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple          # 强制 pip 源
PLAYWRIGHT_DOWNLOAD_HOST=https://registry.npmmirror.com/-/binary/playwright  # 强制 Chromium 源
MC_GIT_URL=https://gh-proxy.com/https://github.com/NanmiCoder/MediaCrawler.git  # 强制克隆地址
mc --setup --no-mirror                                           # 整体禁用镜像，全部直连官方源
```

pip 和 Playwright 的安装进度会逐行转发到 stderr，stdout 始终是纯 JSON。

系统要求：Python ≥ 3.10、git、可访问 GitHub 和 PyPI 的网络；**抖音还需要本机 Node.js ≥ 16**（签名用，`brew install node`），小红书 / 快手 / B 站不需要。没装 mc 命令时可以直接 `ln -sf "$(pwd)/mediacrawler/bin/mc" ~/.local/bin/mc`。

## 登录

```bash
mc search --platform xiaohongshu --keywords "测试词" --max-notes 20
```

首次运行会**弹出浏览器窗口**，在页面里扫码（小红书 App / 抖音 App / 快手 App / B 站 App 扫）。
登录态保存在 `vendor/MediaCrawler/browser_data/{platform}_user_data_dir`，之后免扫码。
`mc --status` 的 `login_state_platforms` 可查哪些平台已经登录过。

- 登录方式：`--login qrcode`（默认）/ `--login phone` / `--login cookie --cookies "web_session=..."`
- **不要加 `--headless`** 跑首次登录（看不见二维码）；登录态就绪后小批量抓取可以加
- 如果扫码后仍卡在登录页（小红书偶发滑块验证），开着窗口手动过一下验证，或删掉 `vendor/MediaCrawler/browser_data/{platform}_user_data_dir` 重来

## 命令

```
mc --status                                 # 安装状态 + 已登录平台（JSON）
mc --setup [--force]                        # 安装/重装

mc search  --platform <平台> --keywords "词1,词2" [--max-notes N]   # find：关键词搜对标
mc detail  --platform <平台> --ids "作品URL或ID, ..."               # crack：作品详情（支持分享短链）
mc creator --platform <平台> --ids "主页URL或ID, ..."               # 账号诊断：抓创作者作品列表

通用：--comments/--no-comments（detail/creator 默认抓；search 默认不抓 —— find 只用
      互动计数，评论计数详情自带；要评论显式加 --comments）
      --max-comments N（每条上限，默认 10，对齐上游）
      --timeout 秒（默认 900）  --out 目录（默认 vendor/mc-data）
```

平台名接受 `xiaohongshu/douyin/kuaishou/bilibili` 或 `xhs/dy/ks/bili`。

**输出**：机器可读 JSON 走 stdout，人类进度（含扫码提示）走 stderr：

```json
{
  "ok": true, "platform": "xhs", "mode": "search", "count": 2,
  "items": [{
    "id": "…", "url": "…（含 xsec_token，可直接打开）", "type": "video|note",
    "title": "…", "desc": "…", "publish_time": 1758002400,
    "liked_count": 1234, "collected_count": 567, "comment_count": 89, "share_count": 12,
    "image_urls": ["…"], "video_url": "…", "cover_url": "…", "tags": ["…"],
    "keyword": "触发搜索的词",
    "comments": [{"content": "…", "like_count": 23, "create_time": 1758002500}]
  }],
  "raw_files": ["…原始 MediaCrawler JSON…"]
}
```

封面 / 视频下载后照常喂 `scripts/analyze_image.py` / `analyze_video.py`，评论直接进 crack 的评论区分析。

## 与 tikhub CLI 的能力对照

| 任务 | tikhub | mc |
|---|---|---|
| 关键词搜笔记/视频 | `xiaohongshu_app_v2_search_notes` 等 | `mc search --keywords "词1,词2"` |
| 作品详情（含分享链接解析） | `*_fetch_one_video` / `*_note_detail` | `mc detail --ids "URL"` |
| 账号作品列表 | `*_get_user_posted_notes` 等 | `mc creator --ids "主页URL"` |
| 评论 | `*_get_note_comments` 等 | search/detail 自带（`--comments`） |
| 账号资料（粉丝数/简介） | `*_get_user_info` 等 | ❌ 上游防骚扰设计不落库，见下 |
| 视频号全流程 | `wechat_channels_v2_*` | ❌ 不支持 |

## 已知边界（来自上游"教学版"设计，勿在报告里当 bug）

1. **创作者身份匿名化**：输出里 `nickname` 脱敏（`小***厨`）、`creator_hash` 是 sha256 截断哈希，**没有真实用户 ID、主页链接、粉丝数、简介**。find Step 5 的体量过滤改用**作品互动量 + 更新频率**近似；需要精确粉丝数时换 TikHub 路径。
2. **没有播放量**（快手搜素有 `view_count`，其他平台搜索结果无播放），诊断判断优先用点赞/收藏/评论。
3. **小红书搜索单次最小 20 条/词**（上游强制 `--max-notes` 下限 20），`--max-notes` 是**每个关键词**的上限。
4. **B 站返回三连细分**（投币/收藏/弹幕），比 TikHub 更全；抖音返回封面和视频直链，可直接下载。

## 合规与频率控制

MediaCrawler 采用 NON-COMMERCIAL LEARNING LICENSE：仅供学习研究，不得商用、不得大规模爬取。

登录的是**用户自己的账号**，抓太密会触发平台风控（验证码、限流甚至封号）。mc 的默认参数已经是保守档（并发 1、每次请求间隔 ≥2s、评论仅 detail/creator 默认抓且每条 ≤10、单次几十条），在此之上还有三道机制保护：

- **同平台 30 分钟冷却**：同一平台两次抓取间隔不足会直接拒绝，报错里提示合并关键词或用 `--force` 覆盖
- **失败退避 10 分钟**：只要浏览器拉起过（无论成败），失败后也会进入短冷却——失败往往发生在风控敏感期，立即重试只会加压
- **同平台文件锁**：并行抓取会抢同一个浏览器登录 profile（可能损坏登录态、要重新扫码），mc 会直接拒绝并行进程；崩溃残留的锁 2 小时后自动失效

另外 `mc` 只把**本次 run 新写出的数据文件**当结果：抓取失败没产出新文件时报 `stale_data` 并列出历史文件的路径和年龄，不会把昨天的数据静默当今天的结果返回。

人工使用时同样遵守：

1. **合并请求**：多个关键词合成一次 `--keywords "词1,词2"`，多条链接合成一次 `--ids`，不要拆成多次调用
2. **单次上限**：search ≤ 3 词、detail ≤ 5 条、creator ≤ 2 个账号；不要并行跑多个 mc
3. **每日预算**：同账号同平台每天 ≤ 4-6 次 run——风控看的是长期总量，不是单次频率；额度用完改走 TikHub 或改天再跑
4. **先复用再抓**：`vendor/mc-data/` 24 小时内的同关键词/同账号数据先复用，不重复抓
5. **见好就收**：出现验证码、登录失效、连续空结果、`stale_data` 立即停手，换时间再试
6. 确有必要立即重抓时才用 `--force`；冷却时长可用 `MC_COOLDOWN_SECONDS` / `MC_FAILURE_COOLDOWN_SECONDS` 环境变量调整

> ⚠️ `--login cookie --cookies "..."` 的 cookie 串会出现在进程列表（`ps`）里，多用户共享的机器慎用；扫码登录没有这个问题。
