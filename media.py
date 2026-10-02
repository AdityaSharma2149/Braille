"""Offline media engines for Sparsh: image OCR and speech-to-text.

Everything here runs on the local machine -- no image or recording is ever
sent to a cloud service. That keeps image scanning and voice input working in
any browser (including privacy browsers that disable Google's Web Speech API)
and with no internet connection after the engines are installed.

OCR backend order:
    1. the system ``tesseract`` binary, if it is installed
    2. ``rapidocr-onnxruntime`` (pip-only, ships its own ONNX models)
Speech-to-text backend:
    ``faster-whisper`` running a small Whisper model on CPU
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


def _tesseract_binary() -> str | None:
    return shutil.which('tesseract')


@lru_cache(maxsize=1)
def _rapidocr():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel

    size = os.environ.get('SPARSH_WHISPER_MODEL', 'base')
    return WhisperModel(size, device='cpu', compute_type='int8')


def ocr_available() -> bool:
    if _tesseract_binary():
        return True
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def speech_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _enlarge(image):
    """Upscale small images so thin glyphs survive recognition."""
    import cv2

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest < 1000:
        scale = min(6.0, 1000 / longest)
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return image


def _prepare_math_image(gray):
    """Normalize polarity, binarize, and tighten horizontal gaps.

    OCR models drop an isolated ``=`` when it is surrounded by spaces
    ("2x + 3 = 11" reads as "2x + 3" and "11"), which makes equations
    unsolvable. Collapsing the wide blank columns between glyphs back to a
    small, glyph-relative gap lets the recognizer read the line as one string.
    """
    import cv2
    import numpy as np

    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    if np.median(border) < 128:
        gray = 255 - gray
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = (binary < 128).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(text, 8)
    heights = [h for (_, _, _, h, area) in stats[1:] if area >= 4 and h >= 3]
    glyph = int(np.median(heights)) if heights else 12
    keep = max(3, int(round(glyph * 0.15)))

    has = text.any(axis=0)
    columns = []
    i, count = 0, len(has)
    while i < count:
        if has[i]:
            columns.append(i)
            i += 1
        else:
            j = i
            while j < count and not has[j]:
                j += 1
            columns.extend(range(i, i + min(keep, j - i)))
            i = j
    return binary[:, columns] if columns else binary


def _read_order(result):
    def key(line):
        box = line[0]
        x = min(point[0] for point in box)
        y = min(point[1] for point in box)
        return (round(y / 10), x)

    return sorted(result, key=key)


def _rapidocr_text(raw: bytes) -> str:
    import cv2
    import numpy as np

    array = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if array is None:
        return ''
    prepared = _enlarge(_prepare_math_image(cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)))
    result, _ = _rapidocr()(cv2.cvtColor(prepared, cv2.COLOR_GRAY2RGB), use_cls=False)
    if not result:
        return ''
    return '\n'.join(line[1] for line in _read_order(result)).strip()


def ocr_image(raw: bytes) -> str:
    """Recognize text in raw PNG/JPEG bytes using the best available local engine."""
    binary = _tesseract_binary()
    if binary:
        with tempfile.TemporaryDirectory(prefix='sparsh-') as folder:
            path = Path(folder) / 'input'
            path.write_bytes(raw)
            try:
                result = subprocess.run([binary, str(path), 'stdout', '--psm', '6'], capture_output=True, timeout=25)
            except subprocess.TimeoutExpired:
                raise TimeoutError('Scanning took too long. Try a smaller image.')
            if result.returncode == 0:
                text = result.stdout.decode('utf-8', errors='replace').strip()
                if text:
                    return text
    return _rapidocr_text(raw)


def transcribe_audio(raw: bytes, language: str = 'en') -> str:
    """Transcribe a recording (WebM/Opus, WAV, ...) fully offline on the CPU.

    Voice-activity filtering plus no-speech detection stop quiet or near-silent
    clips from producing Whisper's short filler "hallucinations" (the model
    likes to answer "You" / "Thank you" when it hears no real speech), and the
    result is rejected if it is only such a filler so the app can honestly say
    no speech was detected.
    """
    with tempfile.TemporaryDirectory(prefix='sparsh-') as folder:
        path = Path(folder) / 'input.webm'
        path.write_bytes(raw)
        segments, _ = _whisper().transcribe(
            str(path),
            language=language or None,
            vad_filter=True,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
        text = ' '.join(segment.text.strip() for segment in segments).strip()
    return '' if _is_filler(text) else text


_FILLER = {
    'you', 'thank you', 'thanks', 'thanks for watching', 'thank you for watching',
    'please subscribe', 'subscribe', 'bye', 'bye bye', "you're welcome", 'the end',
    'okay', 'ok', 'so', 'mm', 'hmm', 'hello', 'hi', '.', '..', '...',
}


def _is_filler(text: str) -> bool:
    stripped = re.sub(r"[^\w\s']", '', text).strip().lower()
    return not stripped or stripped in _FILLER
