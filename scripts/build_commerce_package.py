#!/usr/bin/env python3
"""
social-account-doctor: build_commerce_package.py
将 commerce-adapt 的输出（ProductFactCard + 带货文案 + 分镜）打包成结构化 JSON，
供 capsule-cinema、self-media-compliance-review 等下游 Skill 消费。

用法:
    build_commerce_package.py <product_fact.md> <adapt_output.md> [--output commerce-package.json]
    build_commerce_package.py --help

输入:
    product_fact.md    - commerce-product 输出的商品事实卡（Markdown）
    adapt_output.md    - commerce-adapt 输出的带货文案+分镜（Markdown）

输出:
    commerce-package.json — 结构化 JSON，包含:
      - product_fact: ProductFactCard 的结构化表示
      - scripts: 15s/30s/60s 三档口播脚本
      - storyboard: 分镜列表
      - ctas: CTA 候选
      - risk_annotations: 风险标注
      - metadata: 版本/时间戳/来源文件

注意: 本脚本做的是 Markdown → JSON 的结构化提取，不是从零生成内容。
      如果 Markdown 中缺少某些字段，对应的 JSON 字段会标成 null 或空数组。
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional


def read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_section(text: str, heading: str) -> Optional[str]:
    """Extract content under a markdown heading, matching heading text exactly.

    Handles headings with emoji prefixes like '### ⚠️ 待核验' by stripping
    common emoji/symbol prefixes before comparing with the target heading.
    """
    lines = text.split('\n')
    start_idx = None
    for i, line in enumerate(lines):
        m = re.match(r'^[ \t]*(#+)\s+(.*)', line)
        if m:
            heading_text = m.group(2).strip()
            clean = re.sub(r'^[⚠️🚫⛔️🟢🔴🟡✅❌🔹▪️▸►➤\s]+', '', heading_text)
            if clean == heading:
                start_idx = i
                break

    if start_idx is None:
        return None

    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if re.match(r'^[ \t]*#+\s', lines[i]):
            end_idx = i
            break

    return '\n'.join(lines[start_idx + 1:end_idx])


def extract_fact_card(md: str) -> dict:
    """从 ProductFactCard Markdown 中提取结构化字段。"""
    fact_card: dict = {
        "product_url": None,
        "captured_at": None,
        "facts": [],
        "target_audience": [],
        "pain_points": [],
        "selling_points": [],
        "buying_points": [],
        "proof_actions": [],
        "price_and_gifts": [],
        "qualifications": [],
        "risky_claims": [],
        "pending_verification": [],
    }

    url_m = re.search(r"(https?://[^\s\)]+(?:item|product|goods|detail)[^\s\)]*)", md)
    if url_m:
        fact_card["product_url"] = url_m.group(1)

    time_m = re.search(r"抓取时间[：:]\s*(.{10,25})", md)
    if time_m:
        fact_card["captured_at"] = time_m.group(1).strip()

    def extract_list_items(heading: str) -> list[str]:
        section = extract_section(md, heading)
        if not section:
            return []
        items = []
        for line in section.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("- ", "* ", "• ", "├─ ", "└─ ")):
                item = stripped.lstrip("- *•├└─ ").strip()
                if item and not item.startswith("---"):
                    items.append(item)
        return items

    fact_card["facts"] = extract_list_items("商品事实")
    fact_card["target_audience"] = extract_list_items("目标人群")
    fact_card["pain_points"] = extract_list_items("用户痛点")
    fact_card["selling_points"] = extract_list_items("产品卖点")
    fact_card["buying_points"] = extract_list_items("用户买点")
    fact_card["proof_actions"] = extract_list_items("证明动作")
    fact_card["price_and_gifts"] = extract_list_items("价格与活动条件")
    fact_card["qualifications"] = extract_list_items("资质与授权")
    fact_card["risky_claims"] = extract_list_items("禁用表达")
    fact_card["pending_verification"] = extract_list_items("待核验项")

    return fact_card


def extract_scripts(md: str) -> dict:
    """从 commerce-adapt Markdown 中提取三档口播脚本。"""
    scripts: dict = {
        "15s": None,
        "30s": None,
        "60s": None,
    }

    for duration in ("15s", "30s", "60s"):
        pattern = rf"{duration}[：:]\s*[“”「」\"‘’']?(.+?)[“”「」\"‘’']?\s*(?:\n|$)"
        m = re.search(pattern, md)
        if m:
            scripts[duration] = m.group(1).strip().strip("“”「」\"‘’'")

    section = extract_section(md, "口播脚本")
    if section:
        for line in section.split("\n"):
            for duration in ("15s", "30s", "60s"):
                if duration in line and scripts[duration] is None:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        scripts[duration] = parts[1].strip().strip("“”「」\"‘’'")

    return scripts


def extract_storyboard(md: str) -> list[dict]:
    """从 commerce-adapt Markdown 中提取分镜列表。"""
    section = extract_section(md, "分镜提示")
    if not section:
        return []

    shots: list[dict] = []
    shot_pattern = re.compile(
        r"镜(\d+)[：:]\s*"
        r"\[([^\]]+)\]\s*"  # 时间
        r"\[([^\]]+)\]\s*"  # 画面描述
        r"\[([^\]]*)\]\s*"  # 口播对应句
        r"(?:\[([^\]]*)\])?"  # 商品露出方式 (可选)
    )

    for line in section.split("\n"):
        m = shot_pattern.search(line)
        if m:
            shots.append({
                "index": int(m.group(1)),
                "duration": m.group(2).strip(),
                "visual": m.group(3).strip(),
                "dialogue": m.group(4).strip() if m.group(4) else "",
                "product_display": m.group(5).strip() if m.group(5) else None,
            })

    if not shots:
        for line in section.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("镜", "Shot", "shot")):
                shots.append({"raw": stripped})

    return shots


def extract_ctas(md: str) -> list[str]:
    """从 commerce-adapt Markdown 中提取 CTA 候选。"""
    ctas: list[str] = []
    section = extract_section(md, "CTA 候选") or extract_section(md, "CTA")
    if not section:
        return ctas

    for line in section.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ", "1.", "2.", "3.")):
            ctas.append(stripped.lstrip("- *•1234567890. ").strip())

    return ctas


def extract_risks(md: str) -> dict:
    """从 commerce-adapt Markdown 中提取风险标注。"""
    risks: dict = {
        "pending_verification": [],
        "forbidden_expressions": [],
        "price_captured_at": None,
    }

    pending_section = extract_section(md, "待核验")
    if pending_section:
        for line in pending_section.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("- ", "* ", "• ", "⚠️")):
                risks["pending_verification"].append(stripped.lstrip("- *•⚠️ ").strip())

    forbidden_section = extract_section(md, "禁用表达")
    if forbidden_section:
        for line in forbidden_section.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("- ", "* ", "• ", "🚫")):
                risks["forbidden_expressions"].append(stripped.lstrip("- *•🚫 ").strip())

    time_m = re.search(r"价格抓取时间[：:]\s*(.{10,25})", md)
    if time_m:
        risks["price_captured_at"] = time_m.group(1).strip()

    return risks


def extract_titles(md: str) -> list[dict]:
    """从 commerce-adapt Markdown 中提取标题候选。"""
    titles: list[dict] = []
    section = extract_section(md, "标题候选")
    if not section:
        # Try fuzzy match: find any heading containing "标题候选"
        for line in md.split("\n"):
            m = re.match(r'^[ \t]*#+\s+(.*标题候选.*)', line)
            if m:
                heading_text = m.group(1).strip()
                section = extract_section(md, heading_text)
                break
    if not section:
        return titles

    for line in section.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("1.", "2.", "3.")):
            text_match = re.search(r"[“”「」\"'](.+?)[“”「」\"']", stripped)
            title_text = text_match.group(1) if text_match else stripped
            formula_match = re.search(r"公式\s*(\d+)", stripped)
            formula = int(formula_match.group(1)) if formula_match else None
            benefit_match = re.search(r"利益点[「「“](.+?)[」」”]", stripped)
            benefit = benefit_match.group(1) if benefit_match else None

            titles.append({
                "index": len(titles) + 1,
                "text": title_text,
                "formula_id": formula,
                "benefit_point": benefit,
            })

    return titles


def main():
    args = sys.argv[1:]
    output_path = "commerce-package.json"

    positional = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        elif arg in ("--output", "-o") and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif arg.startswith("--output="):
            output_path = arg.split("=", 1)[1]
            i += 1
        else:
            positional.append(arg)
            i += 1

    if len(positional) < 2:
        print(json.dumps({
            "error": "usage: build_commerce_package.py <product_fact.md> <adapt_output.md> [--output commerce-package.json]"
        }, ensure_ascii=False))
        sys.exit(1)

    fact_path = positional[0]
    adapt_path = positional[1]

    if not os.path.exists(fact_path):
        print(json.dumps({"error": f"product fact file not found: {fact_path}"}, ensure_ascii=False))
        sys.exit(2)
    if not os.path.exists(adapt_path):
        print(json.dumps({"error": f"adapt output file not found: {adapt_path}"}, ensure_ascii=False))
        sys.exit(2)

    fact_md = read_file(fact_path)
    adapt_md = read_file(adapt_path)

    package = {
        "metadata": {
            "version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_files": {
                "product_fact": os.path.basename(fact_path),
                "adapt_output": os.path.basename(adapt_path),
            },
        },
        "product_fact": extract_fact_card(fact_md),
        "titles": extract_titles(adapt_md),
        "scripts": extract_scripts(adapt_md),
        "storyboard": extract_storyboard(adapt_md),
        "ctas": extract_ctas(adapt_md),
        "risk_annotations": extract_risks(adapt_md),
    }

    dir_path = os.path.dirname(os.path.abspath(output_path))
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "status": "ok",
        "output": os.path.abspath(output_path),
        "summary": {
            "titles_count": len(package["titles"]),
            "scripts_available": [k for k, v in package["scripts"].items() if v is not None],
            "storyboard_shots": len(package["storyboard"]),
            "ctas_count": len(package["ctas"]),
            "risks_pending": len(package["risk_annotations"]["pending_verification"]),
            "risks_forbidden": len(package["risk_annotations"]["forbidden_expressions"]),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
