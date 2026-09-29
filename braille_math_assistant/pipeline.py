"""
Core pipeline for the Cross-Lingual Spatial Mathematics -> Braille/Audio assistant.

Hybrid architecture (Section 3.2, upgraded):
  1. Ingestion Module        : voice (.wav) transcription (local faster-whisper) +
                               image OCR (OpenCV preprocessing + pytesseract)
  2. Data Integrity Checks   : ocr_accuracy(), ocr_confidence()
  3. Spatial Mathematics Decoding: `spatial_decoder.local_solve()` (engine.py) tries
                               FIRST -- deterministic, offline, zero hallucination.
  4. Semantic Inference Engine: openai/gpt-oss-20b (via Groq) is used ONLY to
     (a) translate an already-solved local answer into a language engine.py doesn't
         natively speak, or
     (b) attempt problems the local engine can't parse at all (flagged unverified).
  5. Tactile Matrix Array + Output: shared Braille matrix from engine.py + gTTS
     localized slow audio.

This file has no side effects on import: nothing calls the network, mic, or
filesystem until you invoke a function.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

import spatial_decoder as sd

# ---------------------------------------------------------------------------
# Tactile Matrix Array -- single source of truth is engine.py (see spatial_decoder.py)
# ---------------------------------------------------------------------------
braille = sd.LOCAL_BRAILLE  # letter/digit -> Unicode Braille cell, reused from engine.py


def text_to_braille(text: str) -> str:
    """Render text as a Braille preview using the SAME matrix engine.py's
    local solver already uses (see spatial_decoder.render_braille), so the
    pipeline's on-screen preview and the local solver's preview never drift.
    """
    return sd.render_braille(text)["text"]


def braille_accuracy(source_text: str, braille_text: str) -> dict:
    """Tactile Translation Fidelity metric (Section 5.1).

    Counts how many *mappable* source characters (present in the shared
    Braille matrix) produced a corresponding Braille cell, vs falling
    through untranslated. Whitespace is not counted as a symbol.
    """
    mappable = [c for c in source_text if c.lower() in braille and not c.isspace()]
    cell_set = set(braille.values())
    mapped_cells = sum(1 for c in braille_text if c in cell_set)
    total = len(mappable)
    accuracy = 100.0 if total == 0 else round(min(mapped_cells, total) / total * 100, 2)
    return {
        "input_symbol_count": total,
        "mapped_symbol_count": min(mapped_cells, total),
        "accuracy_pct": accuracy,
    }


# ---------------------------------------------------------------------------
# Data Integrity Checks (Section 4.2)
# ---------------------------------------------------------------------------
def ocr_accuracy(reference_text: str, extracted_text: str) -> dict:
    """Character survival rate of OCR output against a known reference."""
    ref_chars = [c for c in reference_text if not c.isspace()]
    ext_chars = [c for c in extracted_text if not c.isspace()]
    survived = sum(1 for a, b in zip(ref_chars, ext_chars) if a == b)
    total = len(ref_chars)
    accuracy = 100.0 if total == 0 else round(survived / total * 100, 2)
    return {
        "reference_char_count": total,
        "detected_char_count": len(ext_chars),
        "characters_survived": survived,
        "accuracy_pct": accuracy,
    }


def ocr_confidence(extracted_text: str, min_chars: int = 2) -> bool:
    """Quality gate before spending processing time on garbage OCR output."""
    cleaned = extracted_text.strip()
    letters_digits = sum(1 for c in cleaned if c.isalnum())
    return letters_digits >= min_chars


# ---------------------------------------------------------------------------
# Ingestion Module (Section 3.2 / 4.1)
# ---------------------------------------------------------------------------
def preprocess_image(image_path: str):
    """Clean a photographed textbook page before OCR (Section 6: 'Environmental
    Lighting Sensitivity'). Grayscale -> denoise -> adaptive threshold -> deskew.
    Returns a PIL Image ready for pytesseract.
    """
    import cv2
    import numpy as np
    from PIL import Image

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not read image at {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresholded = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )

    # Deskew: find the dominant text angle from non-zero pixel coordinates.
    coords = np.column_stack(np.where(thresholded < 255))
    angle = 0.0
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) > 0.1:
        (h, w) = thresholded.shape
        matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        thresholded = cv2.warpAffine(
            thresholded, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )

    return Image.fromarray(thresholded)


def ocr_image(image_path: str) -> str:
    """Extract text from a photographed textbook page using pytesseract,
    with OpenCV preprocessing for robustness against poor lighting/skew.
    Falls back to raw pytesseract if OpenCV isn't available.
    """
    import pytesseract

    try:
        image = preprocess_image(image_path)
    except ImportError:
        from PIL import Image

        image = Image.open(image_path)
    return pytesseract.image_to_string(image, config="--psm 6")


@lru_cache(maxsize=1)
def _whisper_model(model_size: str = "small"):
    """Lazily load and cache the local faster-whisper model (offline STT)."""
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe_voice(wav_path: str, language: str = "hi") -> str:
    """Transcribe a .wav voice note fully offline using faster-whisper.

    `language` is a 2-letter ISO code (e.g. 'hi', 'ta', 'en'), not a BCP-47
    locale, since Whisper does not distinguish regional variants.
    Runs on CPU with no API key and no internet after the model is cached
    locally -- this is what actually satisfies the paper's own "off-grid,
    low-resource... no high-speed internet" design constraint (Section:
    Subjects and Settings), which a cloud speech API would not.
    """
    model = _whisper_model()
    segments, _info = model.transcribe(wav_path, language=language)
    return " ".join(segment.text.strip() for segment in segments).strip()


# ---------------------------------------------------------------------------
# Semantic Inference Engine (Section 3.2 / 4.3) -- translation & fallback only
# ---------------------------------------------------------------------------
THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

TRANSLATE_ONLY_PROMPT = (
    "You are a precise translation assistant. Translate the following already-"
    "correct, already-solved math solution into {target_language}. "
    "Do not re-solve it, do not add or remove steps, do not add commentary. "
    "Keep all numbers and mathematical symbols exactly as given. "
    "Reply with only the translated text, no markdown, no reasoning tags."
)

FALLBACK_SOLVE_PROMPT = (
    "You are a math-solving assistant for a blind student. The problem could "
    "not be solved by the local deterministic engine (it may be a word problem, "
    "calculus, or otherwise out of that engine's scope). Solve it step by step, "
    "then write the FINAL step-by-step solution in {target_language}. "
    "Rules: reply in 3-4 short lines maximum, no filler, no restating the "
    "question, no markdown, no reasoning tags, plain text only, one step per line."
)


def strip_reasoning_tags(text: str) -> str:
    """Delete hidden <think>...</think> reasoning blocks (Section 4.3)."""
    return THINK_TAG_RE.sub("", text).strip()


def _groq_chat(
    system_prompt: str,
    user_content: str,
    model: str,
    api_key: str | None,
    client=None,
    reasoning_effort: str = "medium",
) -> str:
    """Single Groq chat completion call at temperature=0. `client` can be
    injected (e.g. a mock) for testing without hitting the network.
    """
    if client is None:
        api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "No GROQ_API_KEY found. Set it with `export GROQ_API_KEY=...` "
                "(get a free key at https://console.groq.com/keys), or pass "
                "api_key= explicitly."
            )
        from groq import Groq

        client = Groq(api_key=api_key)

    # openai/gpt-oss-20b is a reasoning model: it spends tokens on a hidden
    # chain-of-thought (returned separately as `.reasoning`, not `.content`)
    # before writing its final answer. At a low max_tokens budget that hidden
    # reasoning alone can exhaust it, leaving `.content` empty
    # (finish_reason='length') -- confirmed live against the real API.
    # `reasoning_effort='low'` avoids the truncation but was observed live to
    # sometimes skip real translation work (e.g. leaving "Answer:" in
    # English); 'medium' reliably translates fully at a small latency cost.
    # TypeError is caught for mocks/models that don't accept the kwarg.
    kwargs = dict(
        model=model,
        temperature=0,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    try:
        response = client.chat.completions.create(reasoning_effort=reasoning_effort, **kwargs)
    except TypeError:
        response = client.chat.completions.create(**kwargs)

    choice = response.choices[0]
    content = (choice.message.content or "").strip()
    if not content:
        # Confirmed live: a verbose source text can make the model exhaust
        # its whole token budget on hidden reasoning before writing any
        # `.content`. Never surface that raw reasoning trace as if it were
        # the answer (it's an internal monologue, not a translation/solve) --
        # raise instead so the caller can fall back to a known-good result.
        reason = getattr(choice, "finish_reason", "unknown")
        raise RuntimeError(
            f"The AI model returned an empty response (finish_reason={reason}). "
            "This can happen with longer inputs; try again or increase max_tokens."
        )
    return strip_reasoning_tags(content)


LANGUAGE_TO_CODE = {
    "English": "en", "Hindi": "hi", "Tamil": "ta", "Telugu": "te",
    "Kannada": "kn", "Marathi": "mr", "Bengali": "bn", "Gujarati": "gu",
}
LANGUAGE_TLD = {code: (code, "co.in") for code in LANGUAGE_TO_CODE.values()}


@dataclass
class PipelineOutput:
    input_text: str
    solution_text: str
    braille_text: str
    braille_fidelity: dict
    engine: str  # 'local-deterministic' | 'local+llm-translation' | 'llm-fallback (unverified)' | 'local-offline'
    audio_path: str | None = None
    notice: str | None = None


def _solution_text_from_local(result: dict) -> str:
    lines = [step["text"] for step in result["steps"]]
    return "\n".join(lines + [f"Answer: {result['answer']}"])


def run_pipeline(
    question: str,
    target_language: str = "English",
    make_audio: bool = True,
    audio_out: str = "output.mp3",
    model: str = "openai/gpt-oss-20b",
    api_key: str | None = None,
    groq_client=None,
) -> PipelineOutput:
    """Hybrid text-in -> (solution, braille, audio) pipeline (Section 3-4).

    `groq_client` lets tests inject a mock so the hybrid branching logic can
    be verified with zero network calls.
    """
    lang_code = LANGUAGE_TO_CODE.get(target_language, "en")
    native_lang_code = lang_code if lang_code in sd.NATIVE_LANGUAGES else "en"
    notice = None
    engine_tag = "local-deterministic"

    try:
        local_result = sd.local_solve(question, native_lang_code)
        solution_text = _solution_text_from_local(local_result)

        if lang_code not in sd.NATIVE_LANGUAGES:
            # Locally solved, but the student wants a language engine.py
            # doesn't natively speak -> translation-only LLM call.
            try:
                solution_text = _groq_chat(
                    TRANSLATE_ONLY_PROMPT.format(target_language=target_language),
                    solution_text,
                    model,
                    api_key,
                    groq_client,
                )
                engine_tag = "local+llm-translation"
            except RuntimeError as exc:
                notice = f"Offline mode: {exc} Showing solution in {sd.NATIVE_LANGUAGES[native_lang_code]} instead."
                engine_tag = "local-offline"

    except sd.LocalMathError:
        # Local engine can't parse this (word problem, calculus, etc.) ->
        # full LLM solve, clearly flagged as unverified. No local answer
        # exists to fall back to here, so a RuntimeError becomes a plain
        # error message in the output rather than crashing the pipeline.
        try:
            solution_text = _groq_chat(
                FALLBACK_SOLVE_PROMPT.format(target_language=target_language),
                question,
                model,
                api_key,
                groq_client,
            )
            engine_tag = "llm-fallback (unverified)"
        except RuntimeError as exc:
            solution_text = f"Could not get an AI solution: {exc}"
            engine_tag = "error"

    braille_text = text_to_braille(solution_text)
    fidelity = braille_accuracy(solution_text, braille_text)

    audio_path = None
    if make_audio:
        audio_path = synthesize_audio(solution_text, target_language=target_language, out_path=audio_out)

    return PipelineOutput(
        input_text=question,
        solution_text=solution_text,
        braille_text=braille_text,
        braille_fidelity=fidelity,
        engine=engine_tag,
        audio_path=audio_path,
        notice=notice,
    )


def run_worksheet(
    questions: list[str],
    target_language: str = "English",
    make_audio: bool = True,
    audio_dir: str = "worksheet_audio",
    model: str = "openai/gpt-oss-20b",
    api_key: str | None = None,
    groq_client=None,
) -> dict:
    """Batch mode: solve a whole worksheet in one pass (Section: Subjects and
    Settings envisions a full classroom lab, not one question at a time).

    Returns per-question PipelineOutputs plus aggregate engine-usage stats --
    useful evidence for how much of a real worksheet the local deterministic
    engine can handle without ever touching the network or the LLM.
    """
    if make_audio:
        os.makedirs(audio_dir, exist_ok=True)

    outputs = []
    for i, question in enumerate(questions, 1):
        audio_out = os.path.join(audio_dir, f"q{i}.mp3") if make_audio else "output.mp3"
        outputs.append(
            run_pipeline(
                question,
                target_language=target_language,
                make_audio=make_audio,
                audio_out=audio_out,
                model=model,
                api_key=api_key,
                groq_client=groq_client,
            )
        )

    counts: dict[str, int] = {}
    for out in outputs:
        counts[out.engine] = counts.get(out.engine, 0) + 1
    local_only = counts.get("local-deterministic", 0) + counts.get("local-offline", 0) + counts.get("local+llm-translation", 0)

    return {
        "outputs": outputs,
        "engine_counts": counts,
        "total_questions": len(questions),
        "solved_without_llm_math_risk_pct": round(local_only / len(questions) * 100, 2) if questions else 0.0,
    }


# ---------------------------------------------------------------------------
# Output stage: synchronized Braille + slow localized audio (Section 4.4)
# ---------------------------------------------------------------------------
import hashlib

AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".audio_cache")


def synthesize_audio(text: str, target_language: str = "English", out_path: str = "output.mp3") -> str:
    """Render a slow, localized (co.in accent) audio file with gTTS.

    Results are cached by a hash of (text, language) under `.audio_cache/` --
    a repeat question (common in a classroom re-explaining the same problem)
    costs zero extra gTTS calls, which matters on a low-bandwidth school
    connection (Section: Subjects and Settings).
    """
    from gtts import gTTS

    lang_code, tld = LANGUAGE_TLD.get(LANGUAGE_TO_CODE.get(target_language, "en"), ("en", "co.in"))

    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    cache_key = hashlib.sha256(f"{lang_code}|{text}".encode("utf-8")).hexdigest()[:16]
    cache_path = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.mp3")

    if not os.path.exists(cache_path):
        tts = gTTS(text=text, lang=lang_code, tld=tld, slow=True)
        tts.save(cache_path)

    import shutil

    shutil.copyfile(cache_path, out_path)
    return out_path
