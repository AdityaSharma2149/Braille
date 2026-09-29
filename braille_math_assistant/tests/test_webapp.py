import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webapp import Handler


@pytest.fixture(scope="module")
def server_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status, resp.read()


def _post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_health_endpoint(server_url):
    status, body = _get(f"{server_url}/api/health")
    assert status == 200
    assert json.loads(body)["status"] == "ok"


def test_static_pages_served(server_url):
    for path in ["/", "/style.css", "/app.js", "/worksheet.html", "/about.html"]:
        status, _ = _get(server_url + path)
        assert status == 200, path


def test_path_traversal_blocked(server_url):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(f"{server_url}/../webapp.py")
    assert exc_info.value.code in (403, 404)


def test_solve_local_question(server_url):
    status, body = _post(f"{server_url}/api/solve", {"question": "2*x + 3 = 11", "target_language": "English", "make_audio": False})
    assert status == 200
    assert body["engine"] == "local-deterministic"
    assert "x = 4" in body["solution_text"]
    assert body["braille_fidelity"]["accuracy_pct"] == 100.0


def test_solve_empty_question_rejected(server_url):
    status, body = _post(f"{server_url}/api/solve", {"question": ""})
    assert status == 400
    assert "error" in body


def test_worksheet_endpoint(server_url):
    status, body = _post(f"{server_url}/api/worksheet", {"questions": ["2*x + 3 = 11", "sqrt(16) + 9"], "target_language": "English"})
    assert status == 200
    assert body["total_questions"] == 2
    assert body["solved_without_llm_math_risk_pct"] == 100.0
    assert len(body["results"]) == 2


def test_unknown_endpoint_404(server_url):
    status, body = _post(f"{server_url}/api/does-not-exist", {})
    assert status == 404
