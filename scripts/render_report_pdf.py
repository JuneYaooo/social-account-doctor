#!/usr/bin/env python3
"""Render a Markdown diagnosis report to PDF via headless Chrome.

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
    - python: markdown-it-py
    - system: google-chrome (headless mode)
    - fonts:  Source Han Sans SC (思源黑体) installed system-wide for CJK
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import re
import subprocess
import sys
from pathlib import Path

try:
    from markdown_it import MarkdownIt
except ImportError:
    sys.exit("ERROR: markdown-it-py not installed. Run: pip install markdown-it-py")


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


def render(md_path: Path, pdf_path: Path, keep_html: bool = False) -> Path:
    base_dir = md_path.parent
    md_text = md_path.read_text(encoding="utf-8")

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

    proc = subprocess.run(
        ["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}",
         f"file://{html_path}"],
        capture_output=True, text=True, timeout=120,
    )
    if not pdf_path.exists():
        print(proc.stderr[-2000:], file=sys.stderr)
        sys.exit("ERROR: chrome did not produce a PDF")

    if not keep_html:
        html_path.unlink()
    return pdf_path


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render a markdown report to PDF via headless Chrome.",
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

    render(md_path, pdf_path, keep_html=args.keep_html)
    print(f"PDF: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
