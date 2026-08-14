import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = REPO_ROOT / "scripts" / "render_report_pdf.py"
    spec = importlib.util.spec_from_file_location("render_report_pdf", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_markdown_to_plain_text_preserves_report_content():
    module = load_script()
    text = module.markdown_to_plain_text(
        "# 标题\n\n- **卖点**：独立包装\n\n[证据](artifact.json)"
    )
    assert "标题" in text
    assert "• 卖点：独立包装" in text
    assert "证据 (artifact.json)" in text


def test_render_with_cupsfilter_writes_pdf(tmp_path, monkeypatch):
    module = load_script()
    output = tmp_path / "report.pdf"
    calls = []

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/sbin/cupsfilter")

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"%PDF-1.3\nmock", stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module.render_with_cupsfilter("# 标题\n\n正文", output)

    assert output.read_bytes().startswith(b"%PDF")
    assert calls[0][0][:3] == ["/usr/sbin/cupsfilter", "-m", "application/pdf"]


def test_sanitize_markdown_for_export_removes_machine_paths():
    module = load_script()
    markdown = """# 报告

- 素材：`/Users/june2/code/data/tmp/baokuan/case1/video.mp4`
- 产物：`/Users/june2/code/github/social-account-doctor/output/video_distillation/run/00_source/media_info.json`
- 草稿：`/tmp/whisper-case1/audio.txt`
- 其他：`/opt/private-tool/cache.json`
"""

    sanitized = module.sanitize_markdown_for_export(markdown)

    assert "/Users/" not in sanitized
    assert "/tmp/" not in sanitized
    assert "/opt/" not in sanitized
    assert "~/" not in sanitized
    assert "用户上传素材（video.mp4）" in sanitized
    assert "媒体信息核验记录" in sanitized
    assert "临时分析文件（不随报告分发）" in sanitized

    report_fragment = module.sanitize_markdown_for_export(
        "音频转写：`.../02_transcript/transcript.txt`；"
        "原始 Whisper 草稿：`/tmp/whisper-case1/audio.txt`"
    )
    assert "音频转写记录" in report_fragment
    assert "原始转写草稿已完成清理" in report_fragment
    assert "Whisper" not in report_fragment


def test_sanitize_preserves_image_source_while_hiding_visible_paths():
    module = load_script()
    source = "../output/video_distillation/run/03_keyframes/frame.jpg"
    markdown = f"![0.6 秒：钩子画面]({source})\n\n素材路径：`/Users/name/video.mp4`"

    sanitized = module.sanitize_markdown_for_export(markdown)

    assert f"![0.6 秒：钩子画面]({source})" in sanitized
    assert "/Users/" not in sanitized


def test_sanitize_removes_client_preface_but_preserves_conclusion_quote():
    module = load_script()
    markdown = """# 蜂巢小蛋糕爆款视频拆解

> 基于 26.53 秒原视频逐段复核。本报告分析的是内容机制，不把播放、销量或结算金额归因于这条视频。

## 一页结论

> 一句话结论：视觉证明强，购买收口弱。
"""

    sanitized = module.sanitize_markdown_for_export(markdown)

    assert "基于 26.53 秒原视频" not in sanitized
    assert "本报告分析的是内容机制" not in sanitized
    assert "## 一页结论" in sanitized
    assert "一句话结论：视觉证明强，购买收口弱" in sanitized


def test_sanitize_removes_internal_sections_and_command_blocks():
    module = load_script()
    markdown = """# 爆款拆解

## 素材证据包

- 文件：`/Users/name/video.mp4`

## 流量逻辑

先用结果画面建立期待。

```bash
python3 scripts/analyze_video.py ./video.mp4
```

```text
结果画面 → 差异证明 → 使用场景
```
"""

    sanitized = module.sanitize_markdown_for_export(markdown)

    assert "素材证据包" not in sanitized
    assert "文件：" not in sanitized
    assert "python3" not in sanitized
    assert "流量逻辑" in sanitized
    assert "结果画面 → 差异证明 → 使用场景" in sanitized


def test_render_with_fpdf_produces_structured_cjk_pdf(tmp_path):
    module = load_script()
    if module.FPDF is None or not module.find_cjk_font():
        pytest.skip("fpdf2 or a CJK font is unavailable")

    output = tmp_path / "report.pdf"
    module.render_with_fpdf(
        """# 带货视频分析

> 完整度：实际视频已取得。

## 结果概览

| 项目 | 结论 |
|---|---|
| 类目 | 零食糕点 |
| 结构 | 钩子到证明 |

1. 首帧展示真实产品。
2. 中段给出证明动作。
""",
        output,
    )

    assert output.read_bytes().startswith(b"%PDF")
    assert output.stat().st_size > 10_000
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        extracted = subprocess.run(
            [pdftotext, str(output), "-"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "带货视频分析" in extracted
        assert "零食糕点" in extracted


def test_render_with_fpdf_embeds_keyframe_gallery(tmp_path):
    module = load_script()
    if module.FPDF is None or not module.find_cjk_font():
        pytest.skip("fpdf2 or a CJK font is unavailable")

    from PIL import Image

    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (360, 640), color=(210, 48, 92)).save(frame)
    output = tmp_path / "gallery.pdf"
    module.render_with_fpdf(
        "# 画面拆解\n\n![0-3 秒：结果画面](frame.jpg)\n",
        output,
        base_dir=tmp_path,
    )

    content = output.read_bytes()
    assert content.startswith(b"%PDF")
    assert b"/Subtype /Image" in content


def test_render_does_not_accept_stale_pdf_after_browser_failure(tmp_path, monkeypatch):
    module = load_script()
    markdown = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    markdown.write_text("# 新报告\n\n正文", encoding="utf-8")
    output.write_bytes(b"%PDF-old-stale-output")

    monkeypatch.setattr(module, "find_chrome", lambda: "/usr/bin/fake-chrome")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="browser failed"),
    )

    def fake_fpdf(markdown_text, pdf_path, base_dir=None):
        assert not pdf_path.exists()
        assert base_dir == tmp_path
        pdf_path.write_bytes(b"%PDF-new-structured-output")
        return pdf_path

    monkeypatch.setattr(module, "render_with_fpdf", fake_fpdf)
    module.render(markdown, output)

    assert output.read_bytes() == b"%PDF-new-structured-output"
