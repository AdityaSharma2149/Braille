"""
Accessible web server for the Spatial Math -> Braille + Audio assistant.

No Streamlit: a screen reader needs plain, stable, semantic HTML with real
ARIA live regions -- Streamlit's dynamically-rebuilt React DOM fights that.
This is a small stdlib HTTP server (same pattern as the parent Sparsh app's
app.py) serving a static accessible front-end and a JSON API over pipeline.py.

Run:
    python webapp.py --port 8000
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import mimetypes
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from pipeline import (
    ocr_accuracy,
    ocr_confidence,
    ocr_image,
    run_pipeline,
    run_worksheet,
    transcribe_voice,
)

ROOT = Path(__file__).parent / "web"
MAX_BODY = 12 * 1024 * 1024  # audio/image uploads are base64, ~33% larger than raw


class ApiError(ValueError):
    pass


def _read_json_body(handler: "Handler") -> dict:
    size = int(handler.headers.get("Content-Length", "0"))
    if not 0 < size <= MAX_BODY:
        raise ApiError("Request too large or empty. Please use a smaller file.")
    data = json.loads(handler.rfile.read(size))
    if not isinstance(data, dict):
        raise ApiError("Please send a valid request.")
    return data


def _save_base64(encoded: str, allowed_magic: tuple[bytes, ...], suffix: str) -> str:
    if not isinstance(encoded, str) or not encoded:
        raise ApiError("Missing file data.")
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > 8 * 1024 * 1024:
        raise ApiError("Please use a file smaller than 8 MB.")
    if allowed_magic and not any(raw.startswith(magic) for magic in allowed_magic):
        raise ApiError("Unrecognized file format.")
    fd, path = tempfile.mkstemp(prefix="braille-web-", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    return path


def _audio_data_url(path: str | None) -> str | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:audio/mpeg;base64,{encoded}"


class Handler(BaseHTTPRequestHandler):
    server_version = "BrailleMathWeb/1.0"

    def _send(self, status: int, payload, kind: str = "application/json; charset=utf-8") -> None:
        data = json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload, dict) else payload
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # quieter console
        pass

    # -- static files ------------------------------------------------
    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/health":
            return self._send(200, {"status": "ok", "groq_key_present": bool(os.environ.get("GROQ_API_KEY"))})
        rel = "index.html" if route == "/" else route.lstrip("/")
        path = ROOT / rel
        try:
            resolved = path.resolve()
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            return self._send(404, {"error": "Page not found."})
        if not resolved.is_file():
            return self._send(404, {"error": "Page not found."})
        self._send(200, resolved.read_bytes(), mimetypes.guess_type(str(resolved))[0] or "application/octet-stream")

    # -- JSON API ------------------------------------------------
    def do_POST(self) -> None:
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self._send(403, {"error": "This request must come from this app."})

        temp_files: list[str] = []
        try:
            data = _read_json_body(self)
            route = urlparse(self.path).path

            if route == "/api/solve":
                question = data.get("question", "")
                if not isinstance(question, str) or not question.strip():
                    raise ApiError("Please provide a question.")
                target_language = data.get("target_language", "English")
                make_audio = bool(data.get("make_audio", True))
                audio_path = None
                if make_audio:
                    fd, audio_path = tempfile.mkstemp(prefix="braille-web-audio-", suffix=".mp3")
                    os.close(fd)
                    temp_files.append(audio_path)
                out = run_pipeline(
                    question.strip(),
                    target_language=target_language,
                    make_audio=make_audio,
                    audio_out=audio_path or "output.mp3",
                    api_key=data.get("api_key") or None,
                )
                return self._send(200, {
                    "engine": out.engine,
                    "solution_text": out.solution_text,
                    "braille_text": out.braille_text,
                    "braille_fidelity": out.braille_fidelity,
                    "notice": out.notice,
                    "audio_data_url": _audio_data_url(out.audio_path),
                })

            if route == "/api/ocr":
                path = _save_base64(data.get("image", ""), (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"), ".png")
                temp_files.append(path)
                extracted = ocr_image(path)
                return self._send(200, {
                    "text": extracted.strip(),
                    "confident": ocr_confidence(extracted),
                })

            if route == "/api/ocr_accuracy":
                stats = ocr_accuracy(data.get("reference", ""), data.get("extracted", ""))
                return self._send(200, stats)

            if route == "/api/voice":
                path = _save_base64(data.get("audio", ""), (), ".webm")
                temp_files.append(path)
                language = data.get("language", "en")
                text = transcribe_voice(path, language=language)
                return self._send(200, {"text": text})

            if route == "/api/worksheet":
                questions = data.get("questions", [])
                if not isinstance(questions, list) or not questions:
                    raise ApiError("Please provide at least one question.")
                if len(questions) > 30:
                    raise ApiError("Please limit a worksheet to 30 questions.")
                report = run_worksheet(
                    [str(q) for q in questions],
                    target_language=data.get("target_language", "English"),
                    make_audio=False,
                    api_key=data.get("api_key") or None,
                )
                return self._send(200, {
                    "total_questions": report["total_questions"],
                    "engine_counts": report["engine_counts"],
                    "solved_without_llm_math_risk_pct": report["solved_without_llm_math_risk_pct"],
                    "results": [
                        {
                            "question": o.input_text,
                            "engine": o.engine,
                            "solution_text": o.solution_text,
                            "braille_text": o.braille_text,
                        }
                        for o in report["outputs"]
                    ],
                })

            return self._send(404, {"error": "Endpoint not found."})

        except (ApiError, ValueError, TypeError, binascii.Error) as error:
            return self._send(400, {"error": str(error) or "Invalid input."})
        except RuntimeError as error:
            return self._send(502, {"error": str(error)})
        except Exception:
            return self._send(500, {"error": "Something went wrong. Please try again."})
        finally:
            for path in temp_files:
                try:
                    os.unlink(path)
                except OSError:
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Accessible math assistant ready at http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
