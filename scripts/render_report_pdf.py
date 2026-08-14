#!/usr/bin/env python3
"""Render a Markdown diagnosis report to a portable PDF.

USAGE
    python3 scripts/render_report_pdf.py <input.md> [-o output.pdf] [--keep-html]

DEFAULTS
    Output: <input>.pdf next to the .md file
    Page:   A4, 18mm/14mm margins, Source Han Sans SC for CJK
    Theme:  pink-accent, table-heavy diagnosis style (matches social-account-doctor)

IMAGE EMBEDDING
    Local images referenced as ![alt](path) or <img src="path"> are inlined as
    base64 (path is resolved relative to the .md file). Remote images (http/https)
    are kept as URLs (Chrome will fetch them at print time, may slow rendering).

CARD-STYLE TOP-N OBJECTS
    The CSS includes `.card / .card-img / .card-body / .card-table / .tldr / .verdict`
    classes. To get the rich card layout for a "top N benchmarks" section, embed
    raw HTML directly in your markdown:

        <div class="card">
          <div class="card-img"><img src="./assets/top1.webp"/></div>
          <div class="card-body">
            <h3>🥇 @author</h3>
            <div class="stats">赞 <b>2363</b> · 评 <b>60</b> · 藏 <b>1924</b></div>
            <table class="card-table">
              <tr><th>钩子模板</th><td>...</td></tr>
            </table>
          </div>
        </div>

REQUIREMENTS
    - python: markdown-it-py, fpdf2
    - preferred system: Chrome/Chromium (headless mode)
    - structured fallback: fpdf2 (A4 PDF with headings, tables, lists, and CJK)
    - last-resort macOS fallback: cupsfilter (text-first A4 PDF)
    - fonts:  Source Han Sans SC (思源黑体) installed system-wide for CJK
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from markdown_it import MarkdownIt
except ImportError:
    sys.exit("ERROR: markdown-it-py not installed. Run: pip install markdown-it-py")

try:
    from fpdf import FPDF
    from fpdf.fonts import FontFace
except ImportError:
    FPDF = None
    FontFace = None


CSS = r"""
@page { size: A4; margin: 18mm 14mm; }
body {
  font-family: "Source Han Sans SC", "思源黑体", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  color: #1a1a1a; line-height: 1.55; font-size: 11pt;
  max-width: 760px; margin: 0 auto;
}
h1 { font-size: 22pt; border-bottom: 3px solid #d4145a; padding-bottom: 8px; }
h1 small { font-size: 13pt; color: #666; font-weight: normal; }
h2 { font-size: 15pt; color: #d4145a; margin-top: 28px; border-left: 5px solid #d4145a; padding-left: 10px; }
h3 { font-size: 12pt; margin-bottom: 4px; color: #333; }
blockquote { border-left: 4px solid #aaa; padding: 6px 12px; background: #f6f6f6; color: #555; margin: 8px 0; font-size: 10pt; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 10pt; }
th, td { border: 1px solid #d0d0d0; padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: #fef2f5; font-weight: 600; }
code { background: #f0f0f0; padding: 1px 5px; border-radius: 3px;
       font-family: ui-monospace, "SF Mono", Consolas, monospace; font-size: 9.5pt; }
pre { background: #f6f6f6; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 9pt; }
pre code { background: none; padding: 0; }
ol, ul { padding-left: 22px; }
li { margin: 3px 0; }
hr { border: none; border-top: 1px dashed #ccc; margin: 22px 0; }
img { max-width: 100%; }

/* Diagnosis-specific accent classes (use via inline HTML in markdown) */
.tldr { background: #fff3f5; border: 2px solid #d4145a; border-radius: 6px;
        padding: 12px 16px; margin: 10px 0; }
.tldr h2 { margin-top: 0; border: none; padding-left: 0; color: #d4145a; }
.verdict { font-size: 16pt; font-weight: bold; color: #d4145a; margin: 6px 0 12px; }

/* Card layout for top-N benchmark sections */
.card { display: flex; gap: 12px; border: 1px solid #e0e0e0; border-radius: 6px;
        padding: 10px; margin: 12px 0; page-break-inside: avoid; background: #fafafa; }
.card-img { flex: 0 0 130px; }
.card-img img { width: 130px; max-height: 180px; object-fit: cover;
                border: 1px solid #ccc; border-radius: 4px; }
.card-body { flex: 1; }
.card-body h3 { margin: 0 0 4px 0; font-size: 11.5pt; }
.card-body .form { font-size: 9pt; color: #888; font-weight: normal; }
.stats { font-size: 10pt; color: #444; margin: 3px 0; }
.stats b { color: #d4145a; }
.meta { font-size: 9pt; color: #888; margin: 2px 0 6px; }
.card-table { font-size: 9.5pt; margin: 4px 0 0 0; }
.card-table th { width: 70px; background: #f0f0f0; font-size: 9pt; }
.card-table td { font-size: 9.5pt; }

/* Inline image triplets (e.g. cover/page2/page3 of a note) */
.user-img { display: inline-block; width: 32%; margin: 4px 0.5%;
            vertical-align: top; text-align: center; }
.user-img img { width: 100%; border: 1px solid #ddd; border-radius: 4px; }
.user-img .caption { font-size: 9pt; color: #666; margin-top: 4px; line-height: 1.3; }

.footer { font-size: 9pt; color: #888; margin-top: 30px;
          border-top: 1px solid #eee; padding-top: 10px; }
"""


def embed_image(src: str, base_dir: Path) -> str:
    if src.startswith(("http://", "https://", "data:")):
        return src
    candidate = (base_dir / src).resolve() if not src.startswith("/") else Path(src)
    if not candidate.exists():
        print(f"  ! image not found, kept as-is: {src}", file=sys.stderr)
        return src
    mime, _ = mimetypes.guess_type(str(candidate))
    if not mime:
        mime = "image/png"
    data = base64.b64encode(candidate.read_bytes()).decode()
    return f"data:{mime};base64,{data}"


def find_chrome() -> str | None:
    """Find a browser executable without assuming the Linux command name."""
    configured = os.environ.get("CHROME_BIN", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(
        [
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    )
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) or candidate
        if Path(resolved).is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def markdown_to_plain_text(markdown: str) -> str:
    """Keep a readable text representation for the cupsfilter fallback."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"[图片: \1]", markdown)
    text = re.sub(r"<img[^>]*alt=[\"']([^\"']*)[\"'][^>]*>", r"[图片: \1]", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^\s*```[^\n]*$", "", text, flags=re.M)
    text = re.sub(r"^\s*```\s*$", "", text, flags=re.M)
    normalized_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            line = stripped[1:].lstrip()
        elif stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                continue
            line = "  |  ".join(cells)
        normalized_lines.append(line)
    text = "\n".join(normalized_lines)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.M)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


INTERNAL_SECTION_TITLES = {
    "素材证据包",
    "执行记录",
    "运行记录",
    "运行说明",
    "技术说明",
    "产物路径",
    "调试信息",
}


def strip_internal_sections(markdown: str) -> str:
    """Remove operator-only sections and command blocks from client reports."""
    lines = markdown.splitlines()
    kept: list[str] = []
    skipped_heading_level: int | None = None
    in_fence = False
    fence_lines: list[str] = []

    def flush_fence() -> None:
        nonlocal fence_lines
        content = "\n".join(fence_lines)
        is_command = any(
            re.match(r"^\s*(?:\$\s*)?(?:python3?|tikhub|ffmpeg|curl|wget|pip3?|bash|sh)\b", line)
            for line in fence_lines[1:-1]
        )
        if not is_command:
            kept.extend(fence_lines)
        fence_lines = []

    for line in lines:
        if line.lstrip().startswith("```"):
            if in_fence:
                fence_lines.append(line)
                flush_fence()
                in_fence = False
            else:
                in_fence = True
                fence_lines = [line]
            continue
        if in_fence:
            fence_lines.append(line)
            continue

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            title = re.sub(r"[*_`]", "", heading.group(2)).strip()
            if skipped_heading_level is not None and level <= skipped_heading_level:
                skipped_heading_level = None
            if title in INTERNAL_SECTION_TITLES:
                skipped_heading_level = level
                continue
        if skipped_heading_level is None:
            kept.append(line)

    if fence_lines:
        flush_fence()
    return "\n".join(kept).strip() + "\n"


def sanitize_markdown_for_export(markdown: str) -> str:
    """Remove machine-specific absolute paths from portable reports."""
    image_markup: list[str] = []

    def protect_image(match: re.Match[str]) -> str:
        image_markup.append(match.group(0))
        return f"REPORTIMAGEPLACEHOLDER{len(image_markup) - 1}"

    repo_root = Path(__file__).resolve().parents[1].as_posix().rstrip("/") + "/"
    text = strip_internal_sections(markdown)
    text = re.sub(r"!\[[^\]]*\]\([^\n)]+\)", protect_image, text)
    text = re.sub(r"<img\b[^>]*>", protect_image, text, flags=re.I)
    text = text.replace(repo_root, "")
    text = re.sub(r"/Users/[^/\s]+/code/data/tmp/baokuan/", "本地素材/", text)
    text = re.sub(r"output/video_distillation/[^/\s`]+/", "本次蒸馏产物/", text)
    text = re.sub(r"/tmp/", "临时产物/", text)
    text = re.sub(r"临时产物/[^\s`|;)]+", "临时分析文件（不随报告分发）", text)
    text = re.sub(r"/Users/[^/\s]+/", "本地文件/", text)
    text = re.sub(r"(?<![\w:])/(?:home|opt|private|var)/[^\s`|;)]+", "本地文件（不随报告分发）", text)
    text = re.sub(
        r"本地素材/(?:[^`\s|;)]+/)*([^/`\s|;)]+)",
        r"用户上传素材（\1）",
        text,
    )
    artifact_labels = {
        r"本次蒸馏产物/00_source/media_info\.json": "媒体信息核验记录",
        r"本次蒸馏产物/01_media/video\.mp4": "本次分析留存的视频副本",
        r"\.\.\./02_transcript/transcript\.txt": "音频转写记录",
        r"\.\.\./03_keyframes/keyframe_index\.json": "关键画面索引",
        r"\.\.\./03_keyframes/frames/": "关键画面目录",
    }
    for pattern, label in artifact_labels.items():
        text = re.sub(pattern, label, text)
    text = re.sub(
        r"原始 Whisper 草稿：`?临时分析文件（不随报告分发）`?",
        "原始转写草稿已完成清理",
        text,
    )
    text = re.sub(
        r"\.\.\./05_copy/、\.\.\./06_video_logic/、\.\.\./07_audio_logic/、"
        r"\.\.\./07_production_logic/、\.\.\./08_synthesis/",
        "文案、视频结构、音频、制作与综合分析记录",
        text,
    )
    text = text.replace("`multimodal_status: limited`", "分析完整度：实际视频已取得，部分模型能力受限")
    text = text.replace("`ffprobe + 本地 ASR + 关键帧 + 逐帧视觉复核`", "媒体信息、音频转写、关键画面和逐帧视觉复核")
    text = text.replace("`V3_keyframe_ready`", "关键画面与转写已完成")
    for index, markup in enumerate(image_markup):
        text = text.replace(f"REPORTIMAGEPLACEHOLDER{index}", markup)
    return text


def find_cjk_font() -> str | None:
    configured = os.environ.get("PDF_FONT_PATH", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(
        [
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


class ReportPDF(FPDF if FPDF is not None else object):
    report_title = ""

    def header(self):
        if self.page_no() <= 1:
            return
        self.set_font("ReportCJK", size=8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 5, self.report_title[:52], align="R")
        self.ln(7)

    def footer(self):
        self.set_y(-12)
        self.set_font("ReportCJK", size=8)
        self.set_text_color(125, 125, 125)
        self.cell(0, 5, f"{self.page_no()}/{{nb}}", align="C")


def _inline_text(token) -> str:
    if not getattr(token, "children", None):
        return str(getattr(token, "content", ""))
    parts = []
    for child in token.children:
        if child.type in {"text", "code_inline"}:
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append("\n")
        elif child.type == "image":
            parts.append(f"[图片: {child.content or '素材'}]")
    return "".join(parts).strip()


def _display_weight(value: str) -> int:
    return sum(2 if ord(char) > 127 else 1 for char in value)


def _inline_images(token) -> list[tuple[str, str]]:
    images = []
    for child in getattr(token, "children", None) or []:
        if child.type != "image":
            continue
        src = child.attrGet("src") or ""
        if src:
            images.append((src, child.content.strip() or "关键画面"))
    return images


def _resolve_image_path(src: str, base_dir: Path | None) -> Path | None:
    if src.startswith(("http://", "https://", "data:")):
        return None
    candidate = Path(src) if src.startswith("/") else (base_dir or Path.cwd()) / src
    candidate = candidate.resolve()
    return candidate if candidate.is_file() else None


def render_image_gallery(
    pdf: ReportPDF,
    images: list[tuple[str, str]],
    base_dir: Path | None,
) -> None:
    """Render local keyframes in rows of up to three with concise captions."""
    gap = 4.0
    image_height = 62.0
    caption_height = 13.0
    block_height = image_height + caption_height + 5.0

    for start in range(0, len(images), 3):
        group = images[start:start + 3]
        if pdf.get_y() + block_height > pdf.h - pdf.b_margin:
            pdf.add_page()
        count = len(group)
        cell_width = (pdf.epw - gap * (count - 1)) / count
        row_width = cell_width * count + gap * (count - 1)
        row_x = pdf.l_margin + (pdf.epw - row_width) / 2
        row_y = pdf.get_y()

        for offset, (src, caption) in enumerate(group):
            cell_x = row_x + offset * (cell_width + gap)
            image_path = _resolve_image_path(src, base_dir)
            pdf.set_fill_color(246, 246, 246)
            pdf.rect(cell_x, row_y, cell_width, image_height, style="F")
            if image_path:
                pdf.image(
                    image_path,
                    x=cell_x + 1,
                    y=row_y + 1,
                    w=cell_width - 2,
                    h=image_height - 2,
                    keep_aspect_ratio=True,
                    alt_text=caption,
                )
            else:
                pdf.set_xy(cell_x + 2, row_y + image_height / 2 - 3)
                pdf.set_font("ReportCJK", size=8.5)
                pdf.set_text_color(125, 125, 125)
                pdf.multi_cell(cell_width - 4, 5, "画面未随报告提供", align="C")

            pdf.set_xy(cell_x, row_y + image_height + 1.5)
            pdf.set_font("ReportCJK", size=8.3)
            pdf.set_text_color(75, 75, 75)
            pdf.multi_cell(
                cell_width,
                4.2,
                caption[:48],
                align="C",
                wrapmode="CHAR",
                max_line_height=4.2,
            )

        pdf.set_y(row_y + block_height)
        pdf.set_x(pdf.l_margin)
        pdf.set_font("ReportCJK", size=10)
        pdf.set_text_color(35, 35, 35)


def render_with_fpdf(
    markdown: str,
    pdf_path: Path,
    base_dir: Path | None = None,
) -> Path:
    """Render structured Markdown with embedded CJK fonts and A4 layout."""
    if FPDF is None or FontFace is None:
        raise RuntimeError("fpdf2 not installed")
    font_path = find_cjk_font()
    if not font_path:
        raise RuntimeError("no supported CJK font found; set PDF_FONT_PATH")

    tokens = MarkdownIt("commonmark", {"html": True}).enable("table").parse(markdown)
    title = next(
        (_inline_text(tokens[index + 1]) for index, token in enumerate(tokens[:-1])
         if token.type == "heading_open" and token.tag == "h1"),
        "分析报告",
    )
    pdf = ReportPDF(format="A4", unit="mm")
    pdf.report_title = title
    pdf.set_margins(14, 16, 14)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_font("ReportCJK", fname=font_path)
    pdf.alias_nb_pages()
    pdf.set_title(title)
    pdf.set_author("social-account-doctor")
    pdf.add_page()
    pdf.set_font("ReportCJK", size=10)
    pdf.set_text_color(35, 35, 35)

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open" and index + 1 < len(tokens):
            level = int(token.tag[1]) if token.tag.startswith("h") else 2
            content = _inline_text(tokens[index + 1])
            pdf.ln(3 if level == 1 else 2)
            pdf.set_text_color(181, 15, 74)
            pdf.set_font("ReportCJK", size={1: 20, 2: 15, 3: 12}.get(level, 11))
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                0, {1: 10, 2: 8, 3: 7}.get(level, 6), content,
                align="L", wrapmode="CHAR",
            )
            if level == 1:
                pdf.set_draw_color(181, 15, 74)
                pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.w - pdf.r_margin, pdf.get_y() + 1)
                pdf.ln(3)
            pdf.set_text_color(35, 35, 35)
            pdf.set_font("ReportCJK", size=10)
            index += 3
            continue

        if token.type == "blockquote_open":
            parts = []
            index += 1
            while index < len(tokens) and tokens[index].type != "blockquote_close":
                if tokens[index].type == "inline":
                    parts.append(_inline_text(tokens[index]))
                index += 1
            pdf.set_fill_color(245, 245, 245)
            pdf.set_text_color(85, 85, 85)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                0, 5.7, "\n".join(parts), align="L", fill=True,
                padding=3, wrapmode="CHAR",
            )
            pdf.set_text_color(35, 35, 35)
            pdf.ln(2)
            index += 1
            continue

        if token.type == "table_open":
            rows = []
            row = []
            index += 1
            while index < len(tokens) and tokens[index].type != "table_close":
                current = tokens[index]
                if current.type == "tr_open":
                    row = []
                elif current.type == "inline":
                    row.append(_inline_text(current))
                elif current.type == "tr_close" and row:
                    rows.append(row)
                index += 1
            if rows:
                column_count = max(len(row) for row in rows)
                normalized = [row + [""] * (column_count - len(row)) for row in rows]
                weights = [
                    max(8, min(36, max(_display_weight(row[col]) for row in normalized)))
                    for col in range(column_count)
                ]
                pdf.set_font("ReportCJK", size=8.2 if column_count >= 5 else 9)
                heading_style = FontFace(
                    family="ReportCJK",
                    size_pt=9,
                    color=(45, 45, 45),
                    fill_color=(254, 239, 244),
                )
                with pdf.table(
                    rows=normalized,
                    col_widths=weights,
                    headings_style=heading_style,
                    line_height=5.2,
                    text_align="LEFT",
                    width=pdf.epw,
                ):
                    pass
                pdf.set_font("ReportCJK", size=10)
                pdf.set_x(pdf.l_margin)
                pdf.ln(2)
            index += 1
            continue

        if token.type in {"bullet_list_open", "ordered_list_open"}:
            ordered = token.type == "ordered_list_open"
            list_index = 1
            end_type = "ordered_list_close" if ordered else "bullet_list_close"
            index += 1
            while index < len(tokens) and tokens[index].type != end_type:
                if tokens[index].type == "inline":
                    prefix = f"{list_index}. " if ordered else "• "
                    pdf.set_x(pdf.l_margin + 3)
                    pdf.multi_cell(
                        pdf.epw - 3, 5.7, prefix + _inline_text(tokens[index]),
                        align="L", wrapmode="CHAR",
                    )
                    if ordered:
                        list_index += 1
                index += 1
            pdf.ln(1)
            index += 1
            continue

        if token.type == "paragraph_open" and index + 1 < len(tokens):
            inline_token = tokens[index + 1]
            images = _inline_images(inline_token)
            if images:
                render_image_gallery(pdf, images, base_dir)
                index += 3
                continue
            content = _inline_text(inline_token)
            if content:
                pdf.set_font("ReportCJK", size=10)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 5.9, content, align="L", wrapmode="CHAR")
                pdf.ln(1.2)
            index += 3
            continue

        if token.type in {"fence", "code_block"}:
            pdf.set_fill_color(246, 246, 246)
            pdf.set_font("ReportCJK", size=9)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                0, 5.5, token.content.rstrip(), align="L", fill=True,
                padding=3, wrapmode="CHAR",
            )
            pdf.set_font("ReportCJK", size=10)
            pdf.ln(2)
            index += 1
            continue

        if token.type == "hr":
            pdf.set_draw_color(205, 205, 205)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)

        index += 1

    pdf.output(str(pdf_path))
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError("fpdf2 did not produce a PDF")
    return pdf_path


def render_with_cupsfilter(markdown: str, pdf_path: Path) -> Path:
    """Render a portable, text-first PDF using the macOS print filter."""
    cupsfilter = shutil.which("cupsfilter")
    if not cupsfilter:
        raise RuntimeError("Chrome/Chromium unavailable and cupsfilter not installed")
    with tempfile.TemporaryDirectory(prefix="social_account_pdf_") as tmp:
        text_path = Path(tmp) / "report.txt"
        text_path.write_text(markdown_to_plain_text(markdown), encoding="utf-8")
        proc = subprocess.run(
            [cupsfilter, "-m", "application/pdf", "-o", "media=A4", str(text_path)],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.startswith(b"%PDF"):
            stderr = proc.stderr or b""
            detail = (
                stderr.decode("utf-8", errors="replace")
                if isinstance(stderr, bytes)
                else str(stderr)
            )[-1000:]
            raise RuntimeError(f"cupsfilter failed: {detail}")
        pdf_path.write_bytes(proc.stdout)
    return pdf_path


def render(md_path: Path, pdf_path: Path, keep_html: bool = False) -> Path:
    base_dir = md_path.parent
    md_text = sanitize_markdown_for_export(md_path.read_text(encoding="utf-8"))
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.unlink(missing_ok=True)

    md = (MarkdownIt("commonmark", {"html": True, "linkify": True})
          .enable("table").enable("strikethrough"))
    body = md.render(md_text)

    body = re.sub(
        r'src="([^"]+)"',
        lambda m: f'src="{embed_image(m.group(1), base_dir)}"',
        body,
    )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{md_path.stem}</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""
    html_path = pdf_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    chrome = find_chrome()
    chrome_error = ""
    if chrome:
        timeout = max(5, int(os.environ.get("PDF_RENDER_TIMEOUT_SECONDS", "20")))
        try:
            with tempfile.TemporaryDirectory(prefix="social_account_chrome_") as profile:
                proc = subprocess.run(
                    [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                     "--disable-dev-shm-usage", "--no-first-run",
                     "--no-default-browser-check", "--no-pdf-header-footer",
                     f"--user-data-dir={profile}",
                     f"--print-to-pdf={pdf_path}",
                     f"file://{html_path}"],
                    capture_output=True, text=True, timeout=timeout,
                )
            if proc.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
                if not keep_html:
                    html_path.unlink()
                return pdf_path
            chrome_error = (proc.stderr or "")[-2000:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            chrome_error = str(exc)

    fallback_errors = []
    try:
        result = render_with_fpdf(md_text, pdf_path, base_dir=base_dir)
        print(
            "WARNING: Chrome/Chromium PDF rendering was unavailable; "
            "used structured fpdf2 fallback.",
            file=sys.stderr,
        )
        if chrome_error:
            print(f"  browser detail: {chrome_error[-500:]}", file=sys.stderr)
        if not keep_html:
            html_path.unlink()
        return result
    except Exception as fallback_error:
        fallback_errors.append(f"fpdf2: {fallback_error}")

    try:
        result = render_with_cupsfilter(md_text, pdf_path)
        print(
            "WARNING: Chrome/Chromium and fpdf2 rendering were unavailable; "
            "used cupsfilter text fallback.",
            file=sys.stderr,
        )
        if not keep_html:
            html_path.unlink()
        return result
    except RuntimeError as fallback_error:
        fallback_errors.append(f"cupsfilter: {fallback_error}")
        if not keep_html:
            html_path.unlink(missing_ok=True)
        detail = chrome_error or "; ".join(fallback_errors)
        raise RuntimeError(f"PDF rendering failed: {detail}") from fallback_error


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render a Markdown report to a portable PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("USAGE")[1] if "USAGE" in __doc__ else "",
    )
    ap.add_argument("md", help="Path to markdown report")
    ap.add_argument("-o", "--output", help="Output PDF path (default: <md>.pdf next to input)")
    ap.add_argument("--keep-html", action="store_true",
                    help="Keep the intermediate HTML file alongside the PDF (useful for tweaking CSS)")
    args = ap.parse_args()

    md_path = Path(args.md).expanduser().resolve()
    if not md_path.exists():
        sys.exit(f"Not found: {md_path}")
    pdf_path = (Path(args.output).expanduser().resolve()
                if args.output else md_path.with_suffix(".pdf"))

    try:
        render(md_path, pdf_path, keep_html=args.keep_html)
    except RuntimeError as exc:
        sys.exit(f"ERROR: {exc}")
    print(f"PDF: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
