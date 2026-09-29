"""
Spatial Mathematics Decoding + Tactile Matrix Array module.

This does NOT reimplement math parsing or Braille mapping. It imports the
already-built, already-tested deterministic engine from the parent project
(`../engine.py`) so the two projects share one source of truth instead of
drifting apart. `engine.py` implements exactly what the paper calls the
"Spatial Decoding Hypothesis": a bounded AST parser that groups fractions,
exponents, and matrices into non-linear structural units and speaks them in
English, Hindi, or Tamil -- with zero hallucination risk, entirely offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PARENT_DIR = Path(__file__).resolve().parent.parent
if str(_PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(_PARENT_DIR))

from engine import BRAILLE as LOCAL_BRAILLE  # noqa: E402  (letter/digit -> cell dict)
from engine import MathError as LocalMathError  # noqa: E402
from engine import braille as render_braille  # noqa: E402  (text -> {text, unsupported, notice})
from engine import solve as local_solve  # noqa: E402

# engine.py natively speaks these languages (Section: WORDS dict) without
# needing any LLM call at all.
NATIVE_LANGUAGES = {"en": "English", "hi": "Hindi", "ta": "Tamil"}

__all__ = [
    "local_solve",
    "LocalMathError",
    "LOCAL_BRAILLE",
    "render_braille",
    "NATIVE_LANGUAGES",
]
