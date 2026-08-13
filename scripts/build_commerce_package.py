#!/usr/bin/env python3
"""
Build a validated commerce package from ProductFactCard and commerce-adapt Markdown.

Usage:
    build_commerce_package.py <product_fact.md> <adapt_output.md> [--output commerce-package.json]

Both Markdown headings (``## 标题候选``) and the label-style template in
SKILL.md (``标题候选（3 个...）：``) are supported. The command does not write
an output file unless all delivery-critical fields pass validation.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional


PACKAGE_VERSION = "2.0.0"
BLOCK_NAMES = (
    "商品名称",
    "商品事实",
    "SKU",
    "目标人群",
    "用户痛点",
    "产品卖点",
    "用户买点",
    "证明动作",
    "可用文案",
    "价格与活动条件",
    "资质与授权",
    "禁用表达",
    "待核验项",
    "证据",
    "标题候选",
    "口播脚本",
    "分镜提示",
    "CTA 候选",
    "风险标注",
    "待核验",
    "价格确认时间",
    "价格抓取时间",
)


def read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _clean_label(value: str) -> str:
    value = re.sub(r"^[^\w\u4e00-\u9fff]+", "", value.strip())
    value = re.sub(r"（[^\n]*?）", "", value)
    return value.rstrip("：:").strip()


def _line_label(line: str) -> Optional[tuple[str, str, Optional[int]]]:
    """Return normalized label, inline value and heading level for a block line."""
    heading = re.match(r"^[ \t]*(#+)\s+(.*)$", line)
    level = len(heading.group(1)) if heading else None
    body = heading.group(2).strip() if heading else line.strip()

    for name in BLOCK_NAMES:
        if not _clean_label(body).startswith(name):
            continue
        # Avoid treating prose such as "商品事实必须..." as a block label.
        remainder = _clean_label(body)[len(name):]
        if remainder and not remainder.startswith(("候选", "脚本")):
            continue
        value = ""
        colon = re.search(r"[：:]", body)
        if colon:
            value = body[colon.end():].strip()
        return name, value, level
    return None


def extract_section(text: str, heading: str) -> Optional[str]:
    """Extract a heading or label-style block, accepting parenthetical suffixes."""
    lines = text.splitlines()
    start_idx = None
    start_level = None
    inline_value = ""
    for i, line in enumerate(lines):
        parsed = _line_label(line)
        if parsed and parsed[0] == heading:
            start_idx = i
            inline_value = parsed[1]
            start_level = parsed[2]
            break

    if start_idx is None:
        return None

    content = [inline_value] if inline_value else []
    for line in lines[start_idx + 1:]:
        parsed = _line_label(line)
        if parsed:
            next_level = parsed[2]
            if start_level is None or next_level is None or next_level <= start_level:
                break
        heading_match = re.match(r"^[ \t]*(#+)\s+", line)
        if heading_match and start_level is not None and len(heading_match.group(1)) <= start_level:
            break
        content.append(line)

    result = "\n".join(content).strip()
    return result or None


def has_block(text: str, heading: str) -> bool:
    return any(
        parsed is not None and parsed[0] == heading
        for parsed in (_line_label(line) for line in text.splitlines())
    )


def _list_items(section: Optional[str]) -> list[str]:
    if not section:
        return []
    items = []
    for line in section.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:[-*•]|\d+[.)]|├─|└─)\s*(.+)$", stripped)
        if match:
            item = match.group(1).strip()
            if item and not item.startswith("---"):
                items.append(item)
    if not items and section.strip():
        value = section.strip().strip("[]")
        items = [part.strip() for part in re.split(r"[；;]\s*", value) if part.strip()]
    return items


def _split_fact_source(item: str) -> tuple[str, str, str]:
    match = re.match(r"(.+?)(?:[，,；;]\s*)?来源[：:]\s*(.+)$", item)
    if match:
        fact, source = match.group(1).strip(), match.group(2).strip()
    else:
        fact, source = item.strip(), ""
    confidence = "unknown" if not source else "confirmed"
    if "推断" in item:
        confidence = "inferred"
    if "待核验" in item:
        confidence = "unknown"
    return fact, source, confidence


def _extract_sku(md: str) -> list[dict]:
    """Parse ``name | price | stock`` list rows from the SKU section."""
    sku = []
    for item in _list_items(extract_section(md, "SKU")):
        parts = [part.strip() for part in re.split(r"\s*\|\s*", item)]
        sku.append({
            "name": parts[0],
            "price": parts[1] if len(parts) > 1 and parts[1] else None,
            "stock": parts[2] if len(parts) > 2 and parts[2] else None,
        })
    return sku


def extract_fact_card(md: str) -> dict:
    """Extract the canonical ProductFactCard 2.0 contract."""
    name_m = re.search(r"商品名称\s*[：:]\s*([^\n]+)", md)
    url_m = re.search(r"商品链接\s*[：:]\s*(https?://\S+)", md)
    if not url_m:
        url_m = re.search(r"(https?://[^\s\)]+(?:item|product|goods|detail)[^\s\)]*)", md)
    captured_m = re.search(r"(?:资料确认时间|抓取时间)\s*[：:]\s*([^\n]+)", md)
    valid_until_m = re.search(r"价格有效期(?:至)?\s*[：:]\s*([^\n]+)", md)

    fact_items = _list_items(extract_section(md, "商品事实"))
    facts = []
    evidence = []
    for item in fact_items:
        fact, source, confidence = _split_fact_source(item)
        facts.append({"fact": fact, "source": source, "confidence": confidence})
        if source and source not in evidence:
            evidence.append(source)

    evidence.extend(
        item for item in _list_items(extract_section(md, "证据")) if item not in evidence
    )

    return {
        "product_name": name_m.group(1).strip() if name_m else None,
        "product_url": url_m.group(1).rstrip("，,。") if url_m else None,
        "captured_at": captured_m.group(1).strip() if captured_m else None,
        "price_valid_until": valid_until_m.group(1).strip() if valid_until_m else None,
        "sku": _extract_sku(md),
        "facts_with_sources": facts,
        "target_audience": _list_items(extract_section(md, "目标人群")),
        "pain_points": _list_items(extract_section(md, "用户痛点")),
        "selling_points": _list_items(extract_section(md, "产品卖点")),
        "buying_points": _list_items(extract_section(md, "用户买点")),
        "proof_actions": _list_items(extract_section(md, "证明动作")),
        "usable_copy": _list_items(extract_section(md, "可用文案")),
        "price_and_gifts": _list_items(extract_section(md, "价格与活动条件")),
        "qualifications": _list_items(extract_section(md, "资质与授权")),
        "claims_risk": _list_items(extract_section(md, "禁用表达")),
        "pending_verification": _list_items(extract_section(md, "待核验项")),
        "evidence": evidence,
    }


def _quoted_value(value: str) -> str:
    value = value.strip()
    match = re.match(r"^[「“\"'](.+?)[」”\"'](?:\s*[—-].*)?$", value)
    return match.group(1).strip() if match else value.strip("“”「」\"‘’'")


def extract_scripts(md: str) -> dict:
    scripts = {"15s": None, "30s": None, "60s": None}
    section = extract_section(md, "口播脚本") or md
    for duration in scripts:
        match = re.search(
            rf"(?m)^\s*{duration}\s*[：:]\s*(.+)$",
            section,
        )
        if match:
            scripts[duration] = _quoted_value(match.group(1))
    return scripts


def extract_storyboard(md: str) -> list[dict]:
    section = extract_section(md, "分镜提示")
    if not section:
        return []
    shots = []
    pattern = re.compile(
        r"镜(\d+)[：:]\s*"
        r"[\[［]([^\]］]+)[\]］]\s*"
        r"[\[［]([^\]］]+)[\]］]\s*"
        r"[\[［]([^\]］]*)[\]］]\s*"
        r"(?:[\[［]([^\]］]*)[\]］])?"
    )
    for line in section.splitlines():
        match = pattern.search(line)
        if match:
            shots.append({
                "index": int(match.group(1)),
                "duration": match.group(2).strip(),
                "visual": match.group(3).strip(),
                "dialogue": match.group(4).strip(),
                "product_display": match.group(5).strip() if match.group(5) else None,
            })
    return shots


def extract_ctas(md: str) -> list[str]:
    return [_quoted_value(item) for item in _list_items(extract_section(md, "CTA 候选"))]


def _inline_risk(md: str, label: str) -> list[str]:
    match = re.search(rf"(?m)^\s*[^\w\u4e00-\u9fff]*{label}\s*[：:]\s*(.+)$", md)
    if not match:
        return []
    value = match.group(1).strip().strip("[]")
    return [part.strip() for part in re.split(r"[；;]\s*", value) if part.strip()]


def extract_risks(md: str) -> dict:
    declared = has_block(md, "风险标注")
    pending = _list_items(extract_section(md, "待核验")) or _inline_risk(md, "待核验")
    forbidden = _list_items(extract_section(md, "禁用表达")) or _inline_risk(md, "禁用表达")
    time_m = re.search(r"(?:价格确认时间|价格抓取时间)\s*[：:]\s*([^\n]+)", md)
    return {
        "declared": declared,
        "pending_verification": pending,
        "forbidden_expressions": forbidden,
        "price_captured_at": time_m.group(1).strip() if time_m else None,
    }


def extract_titles(md: str) -> list[dict]:
    section = extract_section(md, "标题候选")
    titles = []
    for item in _list_items(section):
        text_match = re.search(r"[「“\"'](.+?)[」”\"']", item)
        formula_match = re.search(r"公式\s*(\d+)", item)
        benefit_match = re.search(r"利益点[「“](.+?)[」”]", item)
        titles.append({
            "index": len(titles) + 1,
            "text": text_match.group(1) if text_match else item,
            "formula_id": int(formula_match.group(1)) if formula_match else None,
            "benefit_point": benefit_match.group(1) if benefit_match else None,
        })
    return titles


def validate_package(package: dict) -> list[str]:
    errors = []
    fact = package["product_fact"]
    if not fact["product_name"]:
        errors.append("ProductFactCard 缺少商品名称")
    if not fact["captured_at"]:
        errors.append("ProductFactCard 缺少资料确认时间")
    if not fact["facts_with_sources"]:
        errors.append("ProductFactCard 缺少商品事实")
    elif not any(item.get("source") for item in fact["facts_with_sources"]):
        errors.append("商品事实至少需要一条可追溯来源")
    if not package["titles"]:
        errors.append("commerce-adapt 缺少标题候选")
    for duration, script in package["scripts"].items():
        if not script:
            errors.append(f"commerce-adapt 缺少 {duration} 口播脚本")
    if not package["storyboard"]:
        errors.append("commerce-adapt 缺少可解析分镜")
    if not package["ctas"]:
        errors.append("commerce-adapt 缺少 CTA 候选")
    if not package["risk_annotations"]["declared"]:
        errors.append("commerce-adapt 缺少风险标注区（没有风险也要明确写“无”）")
    return errors


def build_package(fact_md: str, adapt_md: str, fact_path: str, adapt_path: str) -> dict:
    return {
        "metadata": {
            "version": PACKAGE_VERSION,
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


def main() -> None:
    args = sys.argv[1:]
    output_path = "commerce-package.json"
    positional = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(__doc__)
            return
        if arg in ("--output", "-o") and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif arg.startswith("--output="):
            output_path = arg.split("=", 1)[1]
            i += 1
        else:
            positional.append(arg)
            i += 1

    if len(positional) != 2:
        print(json.dumps({"error": "usage: build_commerce_package.py <product_fact.md> <adapt_output.md> [--output FILE]"}, ensure_ascii=False))
        sys.exit(1)

    fact_path, adapt_path = positional
    missing = [path for path in positional if not os.path.isfile(path)]
    if missing:
        print(json.dumps({"error": "input file not found", "files": missing}, ensure_ascii=False))
        sys.exit(2)

    package = build_package(read_file(fact_path), read_file(adapt_path), fact_path, adapt_path)
    errors = validate_package(package)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False, indent=2))
        sys.exit(3)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "status": "ok",
        "output": os.path.abspath(output_path),
        "summary": {
            "titles_count": len(package["titles"]),
            "scripts_available": list(package["scripts"]),
            "storyboard_shots": len(package["storyboard"]),
            "ctas_count": len(package["ctas"]),
            "risks_pending": len(package["risk_annotations"]["pending_verification"]),
            "risks_forbidden": len(package["risk_annotations"]["forbidden_expressions"]),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
