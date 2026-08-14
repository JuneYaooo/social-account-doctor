import importlib.util
from pathlib import Path
from types import SimpleNamespace


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
