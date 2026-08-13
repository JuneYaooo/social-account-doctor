"""
Tests for commerce-mode scripts: normalize_metrics.py and build_commerce_package.py.

Run with:
    python -m pytest tests/test_commerce_outputs.py -v
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def load_script(name):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_commerce_skill_keeps_video_links_and_comparative_diagnosis_separate_from_product_links():
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / "references" / "commerce-workflow.md").read_text(encoding="utf-8")

    assert "平台带货视频链接或本地视频" in workflow
    assert "视频链接与商品链接必须分开处理" in skill
    assert "3-5 条同类对标" in skill
    assert "只要求客观拆解时可先完成单条 `crack`" in skill
    assert "真实调用成功" in skill
    assert "不解析在线商品页" in skill


# --- normalize_metrics.py tests ---


def test_bucket_name():
    module = load_script("normalize_metrics")
    assert module.bucket_name(0) == "0-1k"
    assert module.bucket_name(500) == "0-1k"
    assert module.bucket_name(999) == "0-1k"
    assert module.bucket_name(1000) == "1k-10k"
    assert module.bucket_name(5000) == "1k-10k"
    assert module.bucket_name(9999) == "1k-10k"
    assert module.bucket_name(10000) == "10k-100k"
    assert module.bucket_name(100000) == "100k-1M"
    assert module.bucket_name(2000000) == "1M+"


def test_compute_engagement_rate():
    module = load_script("normalize_metrics")
    video = {"metrics": {"views": 10000, "likes": 500, "comments": 100, "shares": 50}}
    er = module.compute_engagement_rate(video)
    assert er == (500 + 100 + 50) / 10000

    video_no_views = {"metrics": {"views": 0, "likes": 10, "comments": 1, "shares": 1}}
    assert module.compute_engagement_rate(video_no_views) is None


def test_compute_median():
    module = load_script("normalize_metrics")
    assert module.compute_median([1, 2, 3, 4, 5]) == 3
    assert module.compute_median([1, 2, 100]) == 2
    assert module.compute_median([]) is None
    assert module.compute_median([42]) == 42


def test_normalize_video_spike_detection():
    module = load_script("normalize_metrics")
    video = {
        "video_id": "test_001",
        "account_id": "acct_1",
        "follower_count": 5000,
        "metrics": {"views": 50000, "likes": 3000, "comments": 150, "shares": 80},
    }
    bucket_medians = {"views": 10000, "engagement_rate": 0.05}
    result = module.normalize_video(video, bucket_medians)

    assert result["vs_baseline"]["views_multiple"] == 5.0
    assert "views_spike_5x" in result["growth_flags"]


def test_normalize_video_full():
    module = load_script("normalize_metrics")
    fixture_path = FIXTURES / "commerce_video.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    videos = data["videos"]

    buckets_data: dict[str, list[dict]] = {}
    for v in videos:
        b = module.bucket_name(v.get("follower_count", 0))
        buckets_data.setdefault(b, []).append(v)

    for b, b_videos in buckets_data.items():
        views_list = [vv["metrics"]["views"] for vv in b_videos if vv["metrics"].get("views", 0) > 0]
        er_list = [module.compute_engagement_rate(vv) for vv in b_videos]
        er_list = [e for e in er_list if e is not None]

        medians = {
            "views": module.compute_median(views_list),
            "engagement_rate": module.compute_median(er_list),
        }

        for vv in b_videos:
            result = module.normalize_video(vv, medians)
            assert result["video_id"] == vv["video_id"]
            assert result["data_completeness"] in ("full", "partial", "missing")

    # video 8 is a clear spike (250k vs median ~12k in 1k-10k bucket)
    v8 = [v for v in videos if v["video_id"] == "7300000000000000008"][0]
    b8 = module.bucket_name(v8["follower_count"])
    b8_videos = [v for v in videos if module.bucket_name(v["follower_count"]) == b8]
    b8_views = [v["metrics"]["views"] for v in b8_videos]
    b8_medians = {"views": module.compute_median(b8_views), "engagement_rate": 0.05}
    r8 = module.normalize_video(v8, b8_medians)
    assert r8["vs_baseline"]["views_multiple"] is not None
    assert r8["vs_baseline"]["views_multiple"] > 3.0
    assert any("spike" in f for f in r8["growth_flags"])


def test_normalize_video_missing_fields():
    module = load_script("normalize_metrics")
    partial_video = {
        "video_id": "partial_001",
        "account_id": "acct_p",
        "follower_count": 3000,
        "metrics": {"views": 5000},
    }
    bucket_medians = {"views": 10000, "engagement_rate": 0.05}
    result = module.normalize_video(partial_video, bucket_medians)
    assert result["data_completeness"] == "partial"
    assert result["vs_baseline"]["engagement_multiple"] == 0.0


def test_account_baseline_is_used_and_reports_missing_buckets():
    module = load_script("normalize_metrics")
    data = {
        "videos": [
            {"video_id": "a1", "account_id": "baseline", "follower_count": 5000,
             "metrics": {"views": 100, "likes": 5, "comments": 0, "shares": 0}},
            {"video_id": "a2", "account_id": "baseline", "follower_count": 5000,
             "metrics": {"views": 300, "likes": 15, "comments": 0, "shares": 0}},
            {"video_id": "target", "account_id": "other", "follower_count": 5000,
             "metrics": {"views": 1000, "likes": 50, "comments": 0, "shares": 0}},
            {"video_id": "other_bucket", "account_id": "other", "follower_count": 50000,
             "metrics": {"views": 2000, "likes": 100, "comments": 0, "shares": 0}},
        ]
    }
    result = module.normalize_dataset(data, "baseline")
    target = next(video for video in result["videos"] if video["video_id"] == "target")
    other_bucket = next(video for video in result["videos"] if video["video_id"] == "other_bucket")

    assert result["baseline"]["mode"] == "account"
    assert result["baseline"]["account_id"] == "baseline"
    assert result["baseline"]["buckets"]["1k-10k"]["views"] == 200
    assert target["vs_baseline"]["views_multiple"] == 5.0
    assert target["baseline_sample_size"] == 2
    assert other_bucket["vs_baseline"]["views_multiple"] is None
    assert any("no baseline samples" in warning for warning in result["warnings"])


def test_unknown_baseline_account_fails():
    module = load_script("normalize_metrics")
    try:
        module.normalize_dataset({"videos": [{"account_id": "a"}]}, "missing")
        assert False, "should have raised"
    except ValueError as exc:
        assert "baseline account not found" in str(exc)


def test_load_input(tmp_path):
    module = load_script("normalize_metrics")
    p = tmp_path / "test.json"
    p.write_text(json.dumps({"videos": []}))
    data = module.load_input(str(p))
    assert data == {"videos": []}

    bad_path = tmp_path / "bad.json"
    bad_path.write_text('{"no_videos": 1}')
    try:
        module.load_input(str(bad_path))
        assert False, "should have raised"
    except ValueError:
        pass


# --- build_commerce_package.py tests ---


def test_extract_fact_card_from_markdown():
    module = load_script("build_commerce_package")
    md = """
# 商品事实卡

商品名称: 测试玻尿酸精华

商品链接: https://example.com/product/123

抓取时间: 2026-08-10T14:30:00

## 商品事实
- 产品含有透明质酸成分，来源：详情页第3屏
- 规格为30ml/瓶，来源：SKU选择区

## SKU
- 30ml/瓶 | 99.00 | 有货

## 目标人群
- 25-35岁女性
- 干性/混干肤质

## 用户痛点
- 皮肤干燥起皮
- 底妆卡粉不服帖

## 产品卖点
- 3重玻尿酸复配
- 无酒精无香精

## 禁用表达
- 不能声称"补水效果100%"
- 不能声称"适合所有肤质"

## 待核验项
- 详情页未展示成分表完整信息
"""
    result = module.extract_fact_card(md)
    assert result["product_name"] == "测试玻尿酸精华"
    assert result["product_url"] == "https://example.com/product/123"
    assert result["captured_at"] == "2026-08-10T14:30:00"
    assert len(result["facts_with_sources"]) >= 1
    assert result["facts_with_sources"][0]["source"] == "详情页第3屏"
    assert result["sku"][0]["name"] == "30ml/瓶"
    assert len(result["target_audience"]) >= 1
    assert len(result["pain_points"]) >= 1
    assert len(result["selling_points"]) >= 1
    assert len(result["claims_risk"]) >= 1
    assert len(result["pending_verification"]) >= 1


def test_extract_scripts_from_markdown():
    module = load_script("build_commerce_package")
    md = """
# 带货文案

## 口播脚本
15s：「皮肤干到起皮？试试这瓶玻尿酸精华，一滴锁水一整天！」

30s：「你是不是一到秋冬皮肤就干到起皮、底妆卡粉？其实不是粉底的问题，是你少了一步真正的保湿。」

60s：「30岁以后皮肤锁水能力直接砍半——不是危言耸听。这瓶精华用了3重玻尿酸复配，能渗透到皮肤深层补水锁水。」
"""
    scripts = module.extract_scripts(md)
    assert scripts["15s"] is not None
    assert "玻尿酸" in scripts["15s"]
    assert scripts["30s"] is not None
    assert scripts["60s"] is not None


def test_extract_storyboard():
    module = load_script("build_commerce_package")
    md = """
## 分镜提示
镜1：[0-3s] [干燥皮肤特写，手背起皮] [你是不是一到秋冬皮肤就干到起皮？] [无]
镜2：[3-8s] [产品登场，手持展示瓶身] [其实不是粉底的问题] [手持展示]
镜3：[8-18s] [滴管吸取精华液，涂抹在手背] [这瓶精华用了3重玻尿酸复配] [使用过程]
镜4：[18-25s] [使用前后对比，左右分屏] [一滴锁水一整天] [对比展示]
镜5：[25-30s] [产品+价格+赠品信息大字] [现在买还送试用装，链接在评论区] [商品卡]
"""
    shots = module.extract_storyboard(md)
    assert len(shots) == 5
    assert shots[0]["index"] == 1
    assert shots[0]["duration"] == "0-3s"
    assert shots[0]["visual"] == "干燥皮肤特写，手背起皮"
    assert shots[1]["product_display"] == "手持展示"


def test_extract_ctas():
    module = load_script("build_commerce_package")
    md = """
## CTA 候选
1. 链接在评论区，现在买还送试用装，活动到8月15号
2. 想看更多护肤好物，主页每天更新
"""
    ctas = module.extract_ctas(md)
    assert len(ctas) == 2
    assert "链接在评论区" in ctas[0]


def test_extract_risks():
    module = load_script("build_commerce_package")
    md = """
## 风险标注

### ⚠️ 待核验
- 成分表完整信息（详情页未展示）
- 敏感肌适用（无测试报告）

### 🚫 禁用表达
- 不能声称"100%补水"
- 不能声称"所有肤质适用"

价格抓取时间: 2026-08-10 14:30
"""
    risks = module.extract_risks(md)
    assert risks["declared"] is True
    assert len(risks["pending_verification"]) == 2
    assert len(risks["forbidden_expressions"]) == 2
    assert risks["price_captured_at"] == "2026-08-10 14:30"


def test_extract_titles():
    module = load_script("build_commerce_package")
    md = """
## 标题候选（3 个，每个标注命中哪个标题公式 + 用了哪个商品利益点）
1. 「3个成分让干皮变水润，25岁+必看」 — 公式 1 数字+人群+效果 + 利益点「3重玻尿酸复配」
2. 「原来精华液也分真补水假补水」 — 公式 2 反认知钩子 + 利益点「深层渗透补水」
3. 「我是干皮星人，这瓶精华我囤了3瓶」 — 公式 6 身份共鸣 + 利益点「锁水一整天」
"""
    titles = module.extract_titles(md)
    assert len(titles) == 3
    assert titles[0]["formula_id"] == 1
    assert titles[1]["formula_id"] == 2
    assert titles[2]["formula_id"] == 6


def test_extracts_skill_label_template_without_swallowing_annotations():
    module = load_script("build_commerce_package")
    md = """
标题候选（3 个，每个标注公式）：
  1. 「测试标题」 — 公式 1 + 利益点「测试利益点」

口播脚本（15s / 30s / 60s 三档）：
  15s：「十五秒正文」— 只打 1 个核心利益点 + CTA
  30s：「三十秒正文」— 痛点 → 证明 + CTA
  60s：「六十秒正文」— 完整正文

分镜提示（3-5 镜）：
  镜1：[0-3s] [商品特写] [十五秒正文] [手持展示]

CTA 候选（2 个）：
  1. 「去商品卡看看」— 引导商品卡

风险标注：
  ⚠️ 待核验：价格；库存
  🚫 禁用表达：全网最低
  📅 价格确认时间：2026-08-13T00:00:00Z
"""
    assert module.extract_titles(md)[0]["text"] == "测试标题"
    assert module.extract_scripts(md) == {
        "15s": "十五秒正文",
        "30s": "三十秒正文",
        "60s": "六十秒正文",
    }
    assert len(module.extract_storyboard(md)) == 1
    assert module.extract_ctas(md) == ["去商品卡看看"]
    assert module.extract_risks(md)["declared"] is True
    assert module.extract_risks(md)["pending_verification"] == ["价格", "库存"]
    assert module.extract_risks(md)["forbidden_expressions"] == ["全网最低"]


def test_build_full_package(tmp_path):
    module = load_script("build_commerce_package")
    fact_md = tmp_path / "product_fact.md"
    adapt_md = tmp_path / "adapt_output.md"
    output_json = tmp_path / "commerce-package.json"

    fact_md.write_text("""
# 商品事实卡

商品名称: 测试精华

商品链接: https://example.com/product/test

抓取时间: 2026-08-10T14:30:00

## 商品事实
- 产品规格：30ml/瓶，来源：SKU选择区

## 目标人群
- 干性肤质

## 禁用表达
- 不能声称100%有效

## 待核验项
- 成分完整信息
""")

    adapt_md.write_text("""
# 带货文案

## 标题候选
1. 「测试标题」 — 公式 1 + 利益点「测试利益点」

## 口播脚本
15s：「这是15秒口播测试文本。」

30s：「这是30秒口播测试文本，包含更多细节。」

60s：「这是60秒口播测试文本，完整介绍产品从痛点到转化的全过程。」

## 分镜提示
镜1：[0-3s] [测试画面1] [测试口播1] [手持展示]
镜2：[3-8s] [测试画面2] [测试口播2] [使用过程]

## CTA 候选
1. 链接在评论区
2. 主页查看更多

## 风险标注
### ⚠️ 待核验
- 测试待核验项
""")

    old_argv = sys.argv
    try:
        sys.argv = [
            "build_commerce_package.py",
            str(fact_md),
            str(adapt_md),
            "--output", str(output_json),
        ]
        module.main()
    finally:
        sys.argv = old_argv

    assert output_json.exists()
    with open(output_json, encoding="utf-8") as f:
        package = json.load(f)

    assert package["metadata"]["version"] == "2.0.0"
    assert "source_files" in package["metadata"]
    assert package["product_fact"]["product_url"] == "https://example.com/product/test"
    assert len(package["titles"]) == 1
    assert package["scripts"]["15s"] is not None
    assert package["scripts"]["30s"] is not None
    assert package["scripts"]["60s"] is not None
    assert len(package["storyboard"]) == 2
    assert len(package["ctas"]) == 2
    assert len(package["risk_annotations"]["pending_verification"]) == 1


def test_invalid_package_does_not_write_output(tmp_path):
    fact_md = tmp_path / "product_fact.md"
    adapt_md = tmp_path / "adapt_output.md"
    output_json = tmp_path / "commerce-package.json"
    fact_md.write_text("""商品名称: 测试精华
商品链接: https://example.com/product/test
抓取时间: 2026-08-10T14:30:00
## 商品事实
- 产品规格：30ml，来源：详情页
""")
    adapt_md.write_text("## 标题候选\n1. 「只有标题」")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_commerce_package.py"),
         str(fact_md), str(adapt_md), "--output", str(output_json)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    assert '"status": "invalid"' in result.stdout
    assert not output_json.exists()


def test_product_url_is_optional_when_user_evidence_is_present():
    module = load_script("build_commerce_package")
    card = module.extract_fact_card("""
商品名称: 测试精华
资料确认时间: 2026-08-13T00:00:00Z
## 商品事实
- 规格为 30ml，来源：用户上传 SKU 截图第 1 行
""")
    assert card["product_name"] == "测试精华"
    assert card["product_url"] is None
    package = {
        "product_fact": card,
        "titles": [{"text": "测试"}],
        "scripts": {"15s": "a", "30s": "b", "60s": "c"},
        "storyboard": [{"index": 1}],
        "ctas": ["去商品卡看看"],
        "risk_annotations": {"declared": True},
    }
    assert module.validate_package(package) == []


def test_tikhub_key_can_come_from_explicit_skill_env(tmp_path, monkeypatch):
    client_path = REPO_ROOT / "tikhub" / "lib" / "tikhub_client.py"
    spec = importlib.util.spec_from_file_location("test_tikhub_client", client_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    env_file = tmp_path / ".env"
    env_file.write_text("TIKHUB_API_KEY=from-skill-env\n")
    monkeypatch.delenv("TIKHUB_API_KEY", raising=False)
    monkeypatch.setenv("TIKHUB_ENV_FILE", str(env_file))

    assert module.load_api_key() == "from-skill-env"
