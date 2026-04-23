#!/usr/bin/env python3
"""analyze_document.py — 本地文档 → 纯文本 + 结构化画像

用途：compose 命令的素材解析步骤。吃 .md / .txt / .pdf，吐出：
  - full_text：全文（裁剪到 MAX_CHARS）
  - sections：按 H1/H2 或段落分的章节列表
  - key_lines：开头/结尾/看起来像金句的行（候选封面大字）
  - stats：字数 / 行数 / 段落数

PDF 依赖按以下顺序探测（装哪个用哪个）：
  1. pdfplumber
  2. pypdf
  3. fitz (PyMuPDF)
  4. pdftotext CLI（poppler-utils）
全没有 → 给出清晰安装提示后退出非零。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_CHARS = 50_000


def read_text_file(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def read_pdf(p: Path) -> str:
    # try pdfplumber
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(p)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except ModuleNotFoundError:
        pass

    # try pypdf
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(p))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except ModuleNotFoundError:
        pass

    # try PyMuPDF
    try:
        import fitz  # type: ignore

        doc = fitz.open(str(p))
        return "\n".join(page.get_text() for page in doc)
    except ModuleNotFoundError:
        pass

    # fallback: pdftotext CLI
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(p), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    print(
        "ERROR: 没有可用的 PDF 解析器。三选一装一个：\n"
        "  pip install pdfplumber   # 推荐（布局最准）\n"
        "  pip install pypdf        # 纯 Python 轻量\n"
        "  apt install poppler-utils  # pdftotext CLI",
        file=sys.stderr,
    )
    sys.exit(2)


def split_sections(text: str) -> list[dict]:
    # md H1/H2 作为分界；否则按空行段落
    if re.search(r"^#{1,2} ", text, re.MULTILINE):
        parts = re.split(r"^(#{1,2} .+)$", text, flags=re.MULTILINE)
        sections = []
        cur_title = "(前言)"
        for chunk in parts:
            if chunk.startswith("#"):
                cur_title = chunk.lstrip("# ").strip()
            elif chunk.strip():
                sections.append({"title": cur_title, "body": chunk.strip()})
        return sections
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [{"title": f"段落{i+1}", "body": p} for i, p in enumerate(paras)]


def pick_key_lines(text: str, k: int = 10) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    out: list[str] = []
    # 开头 3 行 + 结尾 2 行
    out.extend(lines[:3])
    out.extend(lines[-2:])
    # 看起来像金句的：短、含感叹/反问/数字/引号
    candidates = [
        ln for ln in lines
        if 6 <= len(ln) <= 40
        and re.search(r'[！？!?""“”]|\d', ln)
    ]
    out.extend(candidates[: k - len(out)])
    # 去重保序
    seen: set[str] = set()
    uniq = []
    for ln in out:
        if ln not in seen:
            seen.add(ln)
            uniq.append(ln)
    return uniq[:k]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="本地文档路径 (.md / .txt / .pdf)")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非可读文本")
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS)
    args = ap.parse_args()

    p = Path(args.path).expanduser()
    if not p.is_file():
        print(f"ERROR: 文件不存在: {p}", file=sys.stderr)
        sys.exit(1)

    ext = p.suffix.lower()
    if ext in {".md", ".markdown", ".txt"}:
        text = read_text_file(p)
    elif ext == ".pdf":
        text = read_pdf(p)
    else:
        print(
            f"ERROR: 不支持的扩展名 {ext}。本脚本只吃 .md / .txt / .pdf；\n"
            "  图片走 analyze_image.py，视频走 analyze_video.py。",
            file=sys.stderr,
        )
        sys.exit(1)

    truncated = len(text) > args.max_chars
    if truncated:
        text = text[: args.max_chars]

    sections = split_sections(text)
    key_lines = pick_key_lines(text)
    stats = {
        "chars": len(text),
        "lines": text.count("\n") + 1,
        "paragraphs": len(sections),
        "truncated": truncated,
    }

    if args.json:
        print(
            json.dumps(
                {
                    "path": str(p),
                    "stats": stats,
                    "sections": sections,
                    "key_lines": key_lines,
                    "full_text": text,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print(f"# 素材解析：{p.name}")
    print(f"- 字数 {stats['chars']} / 行数 {stats['lines']} / 段落 {stats['paragraphs']}"
          + ("（已截断）" if truncated else ""))
    print()
    print("## 候选金句 / 封面大字素材")
    for ln in key_lines:
        print(f"- {ln}")
    print()
    print("## 章节")
    for s in sections[:20]:
        body = s["body"][:200].replace("\n", " ")
        print(f"### {s['title']}")
        print(body + ("…" if len(s["body"]) > 200 else ""))
        print()
    if len(sections) > 20:
        print(f"(… 还有 {len(sections) - 20} 个章节未展开，加 --json 看全量)")


if __name__ == "__main__":
    main()
