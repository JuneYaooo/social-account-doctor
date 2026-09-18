import base64
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_png(path):
    img = Image.new("RGBA", (16, 16), (255, 0, 0, 128))
    img.save(path)


def test_analyze_image_normalizes_non_jpeg_payload(tmp_path, monkeypatch):
    module = load_script("analyze_image")
    img_path = tmp_path / "cover.png"
    make_png(img_path)

    b64, mime = module.prepare_image_payload(str(img_path))

    assert mime == "image/jpeg"
    assert base64.b64decode(b64).startswith(b"\xff\xd8")

    monkeypatch.setenv("VIDEO_ANALYSIS_NORMALIZE_IMAGES", "0")
    b64, mime = module.prepare_image_payload(str(img_path))

    assert mime == "image/png"
    assert base64.b64decode(b64).startswith(b"\x89PNG")


def test_analyze_image_retries_with_larger_token_budget(tmp_path, monkeypatch):
    module = load_script("analyze_image")
    img_path = tmp_path / "cover.png"
    make_png(img_path)
    monkeypatch.setenv("VIDEO_ANALYSIS_API_KEY", "test-key")
    monkeypatch.setenv("VIDEO_ANALYSIS_BASE_URL", "https://proxy.example.com/v1")
    calls = []

    def fake_call_once(api_key, base_url, model, b64, mime, max_tokens, timeout_seconds):
        calls.append((max_tokens, timeout_seconds))
        if max_tokens == 8000:
            return {"ok": True, "content": '{"incomplete":', "finish_reason": "length"}
        return {"ok": True, "content": '{"parsed": true}', "finish_reason": "stop"}

    monkeypatch.setattr(module, "_call_once", fake_call_once)

    result = module.analyze(str(img_path), timeout_seconds=7)

    assert result == {"parsed": True}
    assert calls == [(8000, 7), (16000, 7)]


def test_analyze_image_main_supports_batch_paths_and_defaults_to_serial(tmp_path, monkeypatch, capsys):
    module = load_script("analyze_image")
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    first.write_bytes(b"fake-a")
    second.write_bytes(b"fake-b")

    def fake_analyze(path, timeout_seconds=None):
        return {"source": Path(path).name, "timeout": timeout_seconds}

    monkeypatch.setattr(module, "analyze", fake_analyze)
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_image.py", str(first), str(second), "--timeout", "9"],
    )

    module.main()

    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out == [
        {"file": "a.jpg", "source": "a.jpg", "timeout": 9},
        {"file": "b.jpg", "source": "b.jpg", "timeout": 9},
    ]
    assert "concurrency=1" in captured.err


def test_analyze_video_prefers_video_payload_when_video_exists_by_default(tmp_path, monkeypatch):
    module = load_script("analyze_video")
    video_path = tmp_path / "segment.mp4"
    video_path.write_bytes(b"video")
    captured = {}

    monkeypatch.delenv("VIDEO_ANALYSIS_USE_VIDEO_URL", raising=False)
    monkeypatch.setattr(module, "b64_file", lambda path: "video-b64")

    def fake_gemini_chat(messages, max_tokens=2500, temperature=0.2):
        captured["messages"] = messages
        return {"ok": True}

    monkeypatch.setattr(module, "gemini_chat", fake_gemini_chat)

    result = module.call_visual_segment(
        {"index": 0, "duration": 12, "start": 0, "end": 12, "path": str(video_path)},
        total_segs=1,
    )

    user_content = captured["messages"][1]["content"]
    assert result == {"ok": True}
    assert any(part["type"] == "video_url" for part in user_content)
    assert not any(part["type"] == "image_url" for part in user_content)


def test_analyze_video_uses_frame_payload_when_video_url_disabled(tmp_path, monkeypatch):
    module = load_script("analyze_video")
    video_path = tmp_path / "segment.mp4"
    frame_path = tmp_path / "frame.jpg"
    video_path.write_bytes(b"video")
    frame_path.write_bytes(b"frame")
    captured = {}

    monkeypatch.setenv("VIDEO_ANALYSIS_USE_VIDEO_URL", "0")
    monkeypatch.setattr(
        module,
        "extract_even_frames",
        lambda *args, **kwargs: [{"index": 0, "timestamp": 1.5, "path": str(frame_path)}],
    )
    monkeypatch.setattr(module, "b64_image", lambda path: "frame-b64")

    def fake_gemini_chat(messages, max_tokens=2500, temperature=0.2):
        captured["messages"] = messages
        return {"ok": True}

    monkeypatch.setattr(module, "gemini_chat", fake_gemini_chat)

    result = module.call_visual_segment(
        {"index": 0, "duration": 12, "start": 0, "end": 12, "path": str(video_path)},
        total_segs=1,
    )

    user_content = captured["messages"][1]["content"]
    assert result == {"ok": True}
    assert any(part["type"] == "image_url" for part in user_content)
    assert not any(part["type"] == "video_url" for part in user_content)


def test_analyze_video_frame_fallback_errors_when_no_frames_extracted(tmp_path, monkeypatch):
    module = load_script("analyze_video")
    video_path = tmp_path / "segment.mp4"
    video_path.write_bytes(b"video")

    monkeypatch.setenv("VIDEO_ANALYSIS_USE_VIDEO_URL", "0")
    monkeypatch.setattr(module, "extract_even_frames", lambda *args, **kwargs: [])

    def fail_gemini_chat(*args, **kwargs):
        raise AssertionError("gemini_chat should not be called without frame payloads")

    monkeypatch.setattr(module, "gemini_chat", fail_gemini_chat)

    result = module.call_visual_segment(
        {"index": 0, "duration": 12, "start": 0, "end": 12, "path": str(video_path)},
        total_segs=1,
    )

    assert result["segment_index"] == 0
    assert "no frames extracted" in result["error"]


def test_analyze_video_passes_transcript_hint_to_visual_prompt(tmp_path, monkeypatch):
    module = load_script("analyze_video")
    video_path = tmp_path / "segment.mp4"
    video_path.write_bytes(b"video")
    captured = {}

    monkeypatch.setattr(module, "b64_file", lambda path: "video-b64")

    def fake_gemini_chat(messages, max_tokens=2500, temperature=0.2):
        captured["messages"] = messages
        return {"visual_hooks": {"first_3s_description": "宝宝在玩球"}}

    monkeypatch.setattr(module, "gemini_chat", fake_gemini_chat)

    module.call_visual_segment(
        {"index": 0, "duration": 12, "start": 0, "end": 12, "path": str(video_path)},
        total_segs=1,
        transcript_hint="宝宝正在玩静音球，不用担心打扰邻居。",
    )

    prompt = captured["messages"][1]["content"][0]["text"]
    assert "宝宝正在玩静音球" in prompt
    assert "不得套用与转写品类无关的通用案例" in prompt


def test_analyze_video_rejects_domain_swapped_visual_result():
    module = load_script("analyze_video")
    transcript = "宝宝在餐椅上玩吸盘玩具，妈妈喂饭的时候不用一直捡玩具。"
    visual_result = {
        "visual_hooks": {
            "first_3s_description": "打工人展示三个AI工具提高效率",
            "on_screen_text": "手机APP技巧，建议收藏",
        }
    }

    result = module.assess_cross_modal_consistency(transcript, visual_result)

    assert result["status"] == "conflict"
    assert result["transcript_domain"] == "parenting"
    assert {"AI", "工具"}.issubset(set(result["conflict_terms"]))


def test_analyze_video_accepts_visual_result_matching_transcript_domain():
    module = load_script("analyze_video")
    transcript = "花生吃起来又香又脆，独立包装适合当追剧零食。"
    visual_result = {
        "visual_hooks": {
            "first_3s_description": "手部打开花生包装并展示酥脆颗粒",
        }
    }

    result = module.assess_cross_modal_consistency(transcript, visual_result)

    assert result["status"] == "consistent"
    assert result["transcript_domain"] == "food"


def test_ocr_screenshot_normalizes_images_and_builds_urls(tmp_path):
    module = load_script("ocr_screenshot")
    img_path = tmp_path / "screenshot.png"
    make_png(img_path)

    b64, mime = module.encode_image_to_base64(img_path)

    assert mime == "image/jpeg"
    assert base64.b64decode(b64).startswith(b"\xff\xd8")
    assert (
        module.chat_completions_url("https://proxy.example.com/v1")
        == "https://proxy.example.com/v1/chat/completions"
    )
    assert (
        module.gemini_generate_content_url("https://generativelanguage.googleapis.com/v1beta", "gemini", "key")
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent?key=key"
    )


# ---------------------------------------------------------------------------
# no hidden default endpoints: BASE_URL must be explicit (key-exfiltration guard)
# ---------------------------------------------------------------------------

def test_analyze_image_requires_explicit_base_url(tmp_path, monkeypatch):
    module = load_script("analyze_image")
    img_path = tmp_path / "cover.png"
    make_png(img_path)
    monkeypatch.setenv("VIDEO_ANALYSIS_API_KEY", "sk-test")
    monkeypatch.delenv("VIDEO_ANALYSIS_BASE_URL", raising=False)
    result = module.analyze(str(img_path))
    assert "error" in result
    assert "VIDEO_ANALYSIS_BASE_URL" in result["error"]
    assert "daydream" not in result["error"].lower()


def test_gemini_chat_requires_explicit_base_url(monkeypatch):
    module = load_script("analyze_video")
    monkeypatch.setenv("VIDEO_ANALYSIS_API_KEY", "sk-test")
    monkeypatch.delenv("VIDEO_ANALYSIS_BASE_URL", raising=False)
    result = module.gemini_chat([{"role": "user", "content": "hi"}])
    assert "error" in result
    assert "VIDEO_ANALYSIS_BASE_URL" in result["error"]


def test_gemini_chat_reports_missing_key_as_error(monkeypatch):
    module = load_script("analyze_video")
    monkeypatch.delenv("VIDEO_ANALYSIS_API_KEY", raising=False)
    result = module.gemini_chat([{"role": "user", "content": "hi"}])
    assert "error" in result
    assert "VIDEO_ANALYSIS_API_KEY" in result["error"]


def test_sensevoice_requires_explicit_base_url(monkeypatch):
    module = load_script("analyze_video")
    monkeypatch.setenv("AUDIO_TRANSCRIPTION_API_KEY", "sk-test")
    monkeypatch.delenv("AUDIO_TRANSCRIPTION_BASE_URL", raising=False)
    result = module.call_sensevoice([], required=False)
    assert result.get("skipped") is True
    assert "AUDIO_TRANSCRIPTION_BASE_URL" in result["reason"]
    import pytest
    with pytest.raises(RuntimeError, match="AUDIO_TRANSCRIPTION_BASE_URL"):
        module.call_sensevoice([], required=True)


def test_chat_completions_url_accepts_google_official_compat():
    expected = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    for name in ("analyze_image", "analyze_video", "ocr_screenshot"):
        module = load_script(name)
        assert module.chat_completions_url(
            "https://generativelanguage.googleapis.com/v1beta/openai") == expected
        assert module.chat_completions_url(
            "https://proxy.example.com/v1") == "https://proxy.example.com/v1/chat/completions"


def test_no_hardcoded_third_party_endpoints_in_scripts():
    for name in ("analyze_image", "analyze_video", "ocr_screenshot", "analyze_document"):
        src = (REPO_ROOT / "scripts" / f"{name}.py").read_text(encoding="utf-8")
        assert "daydream" not in src.lower(), f"{name}.py still references the removed proxy domain"
