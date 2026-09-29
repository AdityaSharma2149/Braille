"""Sparsh: a local, keyboard-first mathematics learning workspace."""
from pathlib import Path
import argparse
import base64
import binascii
import json
import mimetypes
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
import uvicorn

from engine import MathError, solve

ROOT = Path(__file__).parent / 'static'
MAX_BODY = 9 * 1024 * 1024

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/health')
async def health():
    return {'status': 'ok', 'ocr': bool(shutil.which('tesseract')), 'engine': 'local-exact'}


@app.get('/')
@app.get('/{file_path:path}')
async def get_page(file_path: str = ''):
    path = ROOT / ('index.html' if not file_path else file_path)
    if not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file():
        return JSONResponse({'error': 'Page not found.'}, status_code=404)
    return Response(path.read_bytes(), media_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')


def dispatch_post(route, data):
    try:
        if route == '/api/solve':
            question = data.get('question', '')
            if not isinstance(question, str):
                raise MathError('The question must be text.')
            return 200, solve(question, data.get('language', 'en'))
        if route == '/api/ocr':
            if not shutil.which('tesseract'):
                return 503, {'error': 'Image scanning needs Tesseract. You can still type or speak a question.'}
            encoded = data.get('image', '')
            if not isinstance(encoded, str):
                raise MathError('Choose a PNG or JPEG image.')
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 6 * 1024 * 1024:
                raise MathError('Please choose an image smaller than 6 MB.')
            if not (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff')):
                raise MathError('Please choose a PNG or JPEG image.')
            with tempfile.TemporaryDirectory(prefix='sparsh-') as folder:
                path = Path(folder) / 'input'
                path.write_bytes(raw)
                result = subprocess.run(['tesseract', str(path), 'stdout', '--psm', '6'], capture_output=True, timeout=25)
                if result.returncode:
                    raise MathError('This image could not be read. Try a clearer, smaller image.')
                extracted = result.stdout.decode('utf-8', errors='replace').strip()
                if not extracted:
                    raise MathError('No text was detected. Try better lighting or type your question.')
                return 200, {'text': extracted, 'notice': 'Review the recognized text before solving. OCR can misread signs, fractions, and exponents.'}
        return 404, {'error': 'Endpoint not found.'}
    except (MathError, ValueError, TypeError, binascii.Error) as error:
        return 400, {'error': str(error) or 'Invalid input.'}
    except subprocess.TimeoutExpired:
        return 408, {'error': 'Scanning took too long. Try a smaller image.'}
    except Exception:
        return 500, {'error': 'Something went wrong. Please try again.'}


@app.post('/{route:path}')
async def post_request(route: str, request: Request):
    origin = request.headers.get('Origin')
    if origin and urlparse(origin).netloc != request.headers.get('Host'):
        return JSONResponse({'error': 'This request must come from the Sparsh app.'}, status_code=403)
    try:
        declared_size = int(request.headers.get('Content-Length', '0'))
        if not 0 < declared_size <= MAX_BODY:
            return JSONResponse({'error': 'Please use an image smaller than 6 MB.'}, status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return JSONResponse({'error': 'Please use an image smaller than 6 MB.'}, status_code=413)
        data = json.loads(body)
        if not isinstance(data, dict):
            raise MathError('Please send a valid request.')
    except (MathError, ValueError, TypeError) as error:
        return JSONResponse({'error': str(error) or 'Invalid input.'}, status_code=400)
    status_code, payload = await run_in_threadpool(dispatch_post, f'/{route}', data)
    return JSONResponse(payload, status_code=status_code)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    print(f'Sparsh is ready at http://localhost:{args.port}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port)
