import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import spatial_decoder as sd
from pipeline import (
    braille_accuracy,
    ocr_accuracy,
    ocr_confidence,
    strip_reasoning_tags,
    text_to_braille,
    run_pipeline,
)


# ---------------------------------------------------------------------------
# Braille matrix / fidelity
# ---------------------------------------------------------------------------
def test_text_to_braille_letters():
    assert text_to_braille("cab") == "⠉⠁⠃"


def test_text_to_braille_digits_get_number_sign():
    result = text_to_braille("12")
    assert result.startswith("⠼")


def test_braille_accuracy_full_match():
    text = "cab"
    stats = braille_accuracy(text, text_to_braille(text))
    assert stats["accuracy_pct"] == 100.0


def test_braille_accuracy_empty_input():
    stats = braille_accuracy("", "")
    assert stats["accuracy_pct"] == 100.0


def test_braille_dict_is_shared_with_engine():
    """pipeline.py must not maintain its own drifted copy of the Braille matrix."""
    import pipeline

    assert pipeline.braille is sd.LOCAL_BRAILLE


# ---------------------------------------------------------------------------
# OCR accuracy / confidence
# ---------------------------------------------------------------------------
def test_ocr_accuracy_perfect_match():
    stats = ocr_accuracy("2x+3=11", "2x+3=11")
    assert stats["accuracy_pct"] == 100.0


def test_ocr_accuracy_partial_match():
    stats = ocr_accuracy("2x+3=11", "2x+3=1l")  # OCR misread 1 as l
    assert 0 < stats["accuracy_pct"] < 100.0


def test_ocr_confidence_rejects_empty():
    assert ocr_confidence("") is False
    assert ocr_confidence("!!") is False


def test_ocr_confidence_accepts_real_text():
    assert ocr_confidence("2x + 3 = 11") is True


def test_preprocess_image_runs_on_synthetic_image(tmp_path):
    from PIL import Image, ImageDraw

    from pipeline import preprocess_image

    path = tmp_path / "sample.png"
    img = Image.new("L", (200, 60), color=255)
    ImageDraw.Draw(img).text((10, 15), "2x+3=11", fill=0)
    img.save(path)

    processed = preprocess_image(str(path))
    assert processed.size[0] > 0 and processed.size[1] > 0


# ---------------------------------------------------------------------------
# LLM text cleanup
# ---------------------------------------------------------------------------
def test_strip_reasoning_tags_removes_think_block():
    raw = "<think>let me work this out...</think>x = 4"
    assert strip_reasoning_tags(raw) == "x = 4"


def test_strip_reasoning_tags_noop_when_absent():
    assert strip_reasoning_tags("x = 4") == "x = 4"


# ---------------------------------------------------------------------------
# Spatial decoder reuse (engine.py wiring)
# ---------------------------------------------------------------------------
def test_local_solve_handles_linear_equation():
    result = sd.local_solve("2*x + 3 = 11", "en")
    assert "4" in result["answer"]


def test_local_solve_raises_for_unsupported_problem():
    import pytest

    with pytest.raises(sd.LocalMathError):
        sd.local_solve("integral of x dx")


def test_local_solve_handles_trig_log_and_abs():
    assert sd.local_solve("abs(-5) + 3")["answer"] == "8"
    assert "1" in sd.local_solve("sin(30) + cos(60)")["answer"]
    assert "2" in sd.local_solve("log(100)")["answer"]


# ---------------------------------------------------------------------------
# Hybrid pipeline branching (no network -- Groq client is mocked)
# ---------------------------------------------------------------------------
class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return _FakeResponse(self.reply)


class _FakeChat:
    def __init__(self, reply):
        self.completions = _FakeCompletions(reply)


class _FakeClient:
    def __init__(self, reply="unused"):
        self.chat = _FakeChat(reply)


def test_locally_solvable_native_language_never_calls_llm():
    client = _FakeClient("SHOULD NOT BE USED")
    out = run_pipeline("2*x + 3 = 11", target_language="Hindi", make_audio=False, groq_client=client)
    assert out.engine == "local-deterministic"
    assert client.chat.completions.calls == 0


def test_locally_solvable_non_native_language_calls_translation_llm():
    client = _FakeClient("translated telugu text")
    out = run_pipeline("2*x + 3 = 11", target_language="Telugu", make_audio=False, groq_client=client)
    assert out.engine == "local+llm-translation"
    assert client.chat.completions.calls == 1
    assert out.solution_text == "translated telugu text"


def test_locally_unsolvable_falls_back_to_llm():
    client = _FakeClient("<think>hmm</think>Integral = x^2/2 + C")
    out = run_pipeline("integral of x dx", target_language="English", make_audio=False, groq_client=client)
    assert out.engine == "llm-fallback (unverified)"
    assert client.chat.completions.calls == 1
    assert "<think>" not in out.solution_text


def test_pipeline_output_braille_and_fidelity_present():
    out = run_pipeline("2*x + 3 = 11", target_language="English", make_audio=False)
    assert out.braille_text
    assert 0 <= out.braille_fidelity["accuracy_pct"] <= 100


# ---------------------------------------------------------------------------
# Worksheet (batch) mode
# ---------------------------------------------------------------------------
def test_run_worksheet_reports_engine_breakdown():
    from pipeline import run_worksheet

    questions = ["2*x + 3 = 11", "sqrt(16) + 9", "integral of x dx"]
    client = _FakeClient("<think>hmm</think>Integral = x^2/2 + C")
    report = run_worksheet(questions, target_language="English", make_audio=False, groq_client=client)

    assert report["total_questions"] == 3
    assert report["engine_counts"]["local-deterministic"] == 2
    assert report["engine_counts"]["llm-fallback (unverified)"] == 1
    assert report["solved_without_llm_math_risk_pct"] == round(2 / 3 * 100, 2)
