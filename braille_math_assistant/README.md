# GanitDrishti — Cross-Lingual Spatial Math → Braille + Audio Assistant

("Ganit" = mathematics, "Drishti" = vision/sight.) Implementation of the
pipeline described in the project abstract: a blind student asks a math
question by typing, speaking, or photographing a textbook page, and gets
back a short step-by-step solution as an on-screen Braille preview plus a
slow, localized audio track — optionally translated into a different Indian
language along the way.

## Dashboard elements, in our accessible theme

A reference design (a dark "engine dashboard" aesthetic built for fair-judge
demos) inspired several real features, added here without adopting its low-
contrast, small-text visual style — everything below still uses the same
high-contrast, large-text, screen-reader-first design as the rest of the site:

- **A real engine-status indicator** — `#engine-status` in the header pings
  `/api/health` on load and shows "GanitDrishti Engine: Online" or a plain
  "Offline" message if the server isn't reachable; not a decorative dot.
- **A live audio waveform** while recording (Quick Ask and the manual voice
  panel), drawn from a real `AnalyserNode` on the microphone stream —
  purely a visual confirmation the mic is picking up sound; it's
  `aria-hidden`, since the text status next to it is the real accessibility
  signal.
- **A live in-browser camera viewfinder** ("Use Live Camera" → live
  `<video>` preview → "Capture Photo") as an alternative to uploading a
  file, useful for a desktop webcam or precise page framing; releases the
  camera automatically when you switch modes or ask another question.
- **An honest 2-stage "working" indicator** while solving (Reading your
  question → Getting your answer ready) — deliberately only 2 stages, since
  the backend answers in one request and we don't fake granular progress
  we can't actually verify happened.
- **Live stat tiles** on the result screen: Braille fidelity for every
  answer, plus a Photo Read Confidence tile that only appears when the
  question came from a photograph.

## Hybrid architecture

Every question is tried **locally first**, against the deterministic bounded
solver already built and tested in the parent project's `engine.py`
(reused, not duplicated, via `spatial_decoder.py`). That local engine parses
arithmetic, linear/quadratic equations, and up-to-3×3 matrices, groups
fractions/exponents/matrices into explicit structural units (the "Spatial
Decoding Hypothesis"), and natively speaks English, Hindi, and Tamil — all
with **zero hallucination risk and no internet required**.

The cloud LLM (`openai/gpt-oss-20b` via Groq) is only ever used for one of
two narrower jobs, and the result always says which one happened:

| `engine` tag | What happened |
|---|---|
| `local-deterministic` | Solved and phrased entirely offline, no LLM call. |
| `local+llm-translation` | Solved locally; LLM only *translated* the already-correct text into a language `engine.py` doesn't natively speak. |
| `llm-fallback (unverified)` | Local engine couldn't parse the question (e.g. a word problem or calculus); the LLM solved it end-to-end — **flag this to the student/teacher as unverified.** |
| `local-offline` | Solved locally but no `GROQ_API_KEY`/network was available for the requested translation, so the native-language answer is returned instead. |

## Files

- `spatial_decoder.py` — thin wrapper that imports `../engine.py`'s
  `solve`/`MathError`/`BRAILLE`/`braille` so this project and the parent
  "Sparsh" app share one deterministic math engine instead of drifting apart.
  The shared engine now also covers `abs()`, `log()`, `ln()`, `sin()`,
  `cos()`, `tan()` (degrees) in English, Hindi, and Tamil, on top of
  arithmetic, linear/quadratic equations, and up-to-3×3 matrices.
- `pipeline.py` — the hybrid pipeline: OCR (OpenCV preprocessing +
  pytesseract), offline voice transcription (`faster-whisper`), the
  local-first/LLM-fallback branching in `run_pipeline()`, batch solving via
  `run_worksheet()`, Braille rendering/fidelity, and gTTS synthesis with a
  content-addressed disk cache (`.audio_cache/`) so repeat questions cost
  zero extra network calls. No side effects on import.
- `cli.py` — the menu-driven runner (`1` type / `2` voice / `3` image),
  matching Section 4.1 of the writeup, printing which engine answered.
- `worksheet.py` — batch mode: solve every question in a text file in one
  pass and report what fraction were answered by the verified local engine
  vs. the LLM fallback. Run: `python worksheet.py questions.txt --language Hindi`.
- `webapp.py` + `web/` — an accessibility-first website (plain semantic
  HTML/CSS/JS, no Streamlit — see **Web UI** below for why).
- `benchmark.py` — produces real, offline-measured numbers for Section 5.1
  (see **Benchmark methodology** below) and writes `benchmark_results.json`.
- `notebook.ipynb` — the same pipeline as a Colab-style notebook with the
  input menu, screenshot-ready cells, a worksheet-mode demo, and a results
  section that loads `benchmark_results.json` instead of hardcoded numbers.
- `tests/test_pipeline.py`, `tests/test_benchmark.py` — unit tests covering
  the Braille matrix, OCR helpers, the local solver wiring (incl.
  trig/log/abs), the hybrid branching logic (via a mocked Groq client — no
  network needed), worksheet mode, and the benchmark metrics.
- `tests/test_webapp.py` — spins up `webapp.py` on an ephemeral port and
  hits its real HTTP API (health, solve, worksheet, static files, a
  path-traversal check) with `urllib` — no browser needed.
- `tests/test_accessibility.py` — **real Chromium browser tests** (Playwright)
  against the actual pages: skip-link focus movement, every keyboard
  shortcut (including the step-1/step-2 context-sensitive `Alt+S`), the
  3-step wizard's navigation and validation, live-region correctness
  (assertive vs. polite), that every form control has a label, that focus
  moves to the answer after solving, theme/font persistence, that Step 1
  and Step 3 fit without scrolling at laptop/tablet/phone/small-phone
  viewport sizes, that a 4-step text-size increase doesn't hide content,
  and the worksheet/about pages. See **Testing** below to run these.

## Verified working end-to-end (this session)

Everything below was actually run, not just written:

- `python -m pytest tests/ -v` — **66/66 passed** (unit + HTTP API + real
  Chromium accessibility/layout tests), zero network calls needed.
- `python benchmark.py` — real numbers: **98% OCR accuracy**, **100% Braille
  fidelity**, **50-point structural-ambiguity reduction** (synthetic/rule-based,
  see methodology below).
- `python worksheet.py` on a 5-question sheet (linear equation, sqrt,
  quadratic, trig, matrix) — **100% solved locally**, real MP3 audio
  generated for every question, second run served entirely from
  `.audio_cache/` in 0.09s.
- **Full offline voice pipeline**: generated real speech audio, ran it
  through `faster-whisper` with no internet/API key, got back correct text,
  fed that into the local solver, got a correct Braille+text answer — a
  genuine voice-to-Braille round trip with the LLM never involved.
- The LLM translation/fallback paths (`local+llm-translation`,
  `llm-fallback (unverified)`) are exercised in tests via a mocked Groq
  client; a **live** Groq call needs your own `GROQ_API_KEY` (none was
  available in this environment) — the logic is verified, the live network
  call itself is not.

## Setup

```bash
cd braille_math_assistant
pip install -r requirements.txt
brew install tesseract   # OCR engine (already installed on this machine)
export GROQ_API_KEY=your_key_here   # https://console.groq.com/keys (free tier)
                                     # only needed for translation/fallback paths --
                                     # locally-solvable English/Hindi/Tamil questions
                                     # work with no key and no internet at all.
```

`faster-whisper` downloads a small speech-recognition model the first time
it's used, then runs fully offline after that (no API key, no per-call
network dependency) — this is what actually satisfies the paper's own
"off-grid, low-resource... no high-speed internet" framing, which a cloud
speech API would not.

## Run

```bash
python cli.py
```

### Web UI

```bash
python webapp.py --port 8000
```

Then open `http://localhost:8000`. `GROQ_API_KEY` is read from the server's
environment (`export GROQ_API_KEY=...` before starting) — there's no key
field in the UI, since locally-solvable English/Hindi/Tamil questions need
no key at all, and asking a blind user to paste a password-masked API key
into a form is an accessibility anti-pattern best avoided entirely.

**Why not Streamlit.** An earlier version of this UI was built in Streamlit
with a decorative "classical" theme. Both were replaced: Streamlit re-renders
its UI through a custom React component tree that screen readers handle
poorly (unstable DOM, weak ARIA support, no real control over focus or live
regions), and a low-contrast parchment/serif aesthetic optimized for how a
page *looks* is actively the wrong design brief for a tool meant to be
*used* by blind and low-vision people. `webapp.py` + `web/` is a small
stdlib Python server (`http.server`, the same pattern as the parent Sparsh
app's `app.py`) serving plain, stable, semantic HTML.

**Accessibility choices, and why:**
- **Atkinson Hyperlegible** typeface — designed by the Braille Institute
  specifically to increase legibility for low-vision readers.
- **High contrast** (black/white by default, WCAG AAA-range ratios) instead
  of the earlier muted palette; a light/dark toggle, since different visual
  conditions are helped by different backgrounds.
- **Large targets** — every button/control is at least 64px tall, well
  above the WCAG 44px minimum, with a thick, high-contrast focus ring on
  every interactive element (`:focus-visible`).
- **Independent text-size control** (A− / A / A+) on top of normal browser
  zoom, persisted across visits.
- **Real semantic HTML**, not framework widgets: `<button>`/`<label>`/
  `<fieldset>`/`<legend>` throughout, a skip-to-content link, and
  `aria-live` regions so a screen reader announces status changes and
  results automatically without the user needing to hunt for them.
- **"Read Instructions Aloud"** — an in-browser Web Speech API button that
  reads the page's own instructions on demand, independent of the backend.
- **Speak your question directly in the browser** via `MediaRecorder` (no
  need to find and upload a pre-recorded file) and **take a photo directly**
  via `<input capture="environment">` on mobile — both lower-friction than
  a sighted-user-oriented file picker.
- **Meaning is never colour-only** — every engine-transparency badge is a
  bordered *text* label ("Verified" / "Unverified"), not just a coloured dot.
- **Keyboard operable end-to-end** — full shortcut list below.

**Step-by-step, fit-to-screen layout.** `index.html` is a 3-step wizard —
**Step 1: Ask**, **Step 2: Language**, **Step 3: Result** — with only one
step visible at a time and a `role="status"` step indicator ("Step 2 of 3:
...") announced on every transition. Each step is sized to the viewport
(`min-height`/flex layout, not a fixed pixel height) so normal use never
requires scrolling to find the next control, at any screen size — verified
by real Playwright tests at laptop, tablet, phone, and small-phone
(iPhone SE, 667px tall) viewport sizes. Scrolling is never physically
disabled, though: enlarging the text size can make a step taller than the
screen, and that step scrolls internally rather than losing content —
removing that escape hatch would violate WCAG 1.4.10 (Reflow) for exactly
the low-vision users this app is for. Back/Continue buttons are explicit
(no surprise auto-advancing), and Quick Ask still jumps straight from
Step 1 to Step 3, skipping the manual language step entirely.

**Advanced features, all built for speed and independence, not decoration:**
- **"Fastest Way: Just Speak" (Quick Ask)** — a single big button at the very
  top of the page (the first thing a skip-link/keyboard user reaches).
  Press once, ask your question out loud, press again — it transcribes,
  solves, and reads the answer back automatically. No need to navigate
  radio buttons, select a mode, then press a separate Solve button.
- **"Read Answer Again"** — replays the last spoken answer (or falls back to
  the browser's own speech synthesis if no audio was generated), so a
  student re-explaining a problem to themselves never has to re-solve it.
- **Question history for the session** — every solved question stays in a
  list with its own "Read This Answer Aloud" button, so earlier answers
  stay reachable without re-asking.
- **Remembered language preferences** — your spoken-language and
  answer-language choices are saved between visits (`localStorage`), so a
  returning user doesn't reconfigure the tool every time.
- **Offline shell caching (PWA)** — a service worker caches the page itself
  (`manifest.json` + `sw.js`), so the interface keeps loading reliably on a
  weak connection; `/api/*` calls are always network-only, since solving
  still needs the local server.
- **Full keyboard shortcut set**, always visible under "Keyboard shortcuts"
  (a native `<details>` element, needs no JavaScript to operate):

  | Shortcut | Action |
  |---|---|
  | `Alt+Q` | Start/stop asking by voice (Quick Ask) — Step 1 only |
  | `Alt+1` / `Alt+2` / `Alt+3` | Switch to type / voice / photo input — Step 1 only |
  | `Alt+S` | Continue (Step 1) or Solve (Step 2) — context-sensitive |
  | `Alt+B` | Go back a step (Step 2 → Step 1) |
  | `Alt+R` | Read the last answer again — Step 3 only |
  | `Escape` | Stop any audio or speech currently playing — any step |

Three pages: `index.html` (solve one question), `worksheet.html` (batch
mode), `about.html` (plain-language explanation of how it works and its
honest limitations — no marketing copy).

## Testing

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium   # one-time browser download
python -m pytest tests/ -v
```

This runs three layers, all offline / no `GROQ_API_KEY` needed:
1. **Unit tests** (`test_pipeline.py`, `test_benchmark.py`) — pure functions,
   hybrid branching logic via a mocked Groq client.
2. **HTTP API tests** (`test_webapp.py`) — real requests against a real
   `webapp.py` instance on an ephemeral port.
3. **Real browser tests** (`test_accessibility.py`) — Playwright drives
   actual Chromium against the actual pages: skip-link focus movement,
   every keyboard shortcut, `aria-live="assertive"` vs `"polite"`
   correctness, that every control has a label, that focus lands on the
   answer after solving, theme/font persistence, and the worksheet/about
   pages. This is what actually proves the accessibility claims above,
   rather than just asserting the code that produces them exists.

Not covered by automated tests (needs a human or real hardware): actual
screen-reader software (VoiceOver/NVDA/JAWS) reading the page aloud, and the
`MediaRecorder`/microphone flow (headless Chromium has no real microphone;
this is exercised manually and via the unit-tested `/api/voice` endpoint).

## Run the benchmark (Section 5.1 numbers)

```bash
python benchmark.py   # writes benchmark_results.json
```

### Benchmark methodology (read before citing these numbers)

No live blind-student trial or real classroom camera photos were available
in this environment, so every number is produced by a script against
synthetic/controlled data — each metric's `methodology` field in
`benchmark_results.json` states exactly how it was measured:

- **OCR accuracy** — equation strings rendered as images with Gaussian blur
  + pixel noise simulating poor classroom lighting, then OCR'd and scored
  against the known ground truth. Not real photographs.
- **Braille fidelity** — `braille_accuracy()` run across 10 representative
  solved-expression strings.
- **Spatial comprehension** — a rule-based proxy, not a human-subject trial:
  counts naive linear readings that collapse distinct structural levels
  (e.g. "2^3" read flat as "two three") vs. `engine.speak()`'s output, which
  always inserts explicit grouping markers by construction.

Replace these with real classroom/user-test data before citing them as
human-subject results in a paper or competition submission.

## Notes / honesty about scope

- The "Braille" produced here is a **visual on-screen preview** using
  uncontracted Grade-1 English + digits, not a certified Nemeth/UEB math
  code or Bharati Braille, and a screen cannot raise physical dots — this
  matches the paper's own Limitations (Section 6).
- The local deterministic engine covers arithmetic, linear/quadratic
  equations, and up-to-3×3 matrices; anything beyond that scope routes to
  the cloud LLM and is explicitly tagged `llm-fallback (unverified)` rather
  than presented as guaranteed-correct.
- The semantic inference engine calls Groq's hosted `openai/gpt-oss-20b` at
  `temperature=0` and strips `<think>...</think>` reasoning tags, as
  described in Section 3.2/4.3 — but only for translation/fallback, per the
  hybrid architecture above.
