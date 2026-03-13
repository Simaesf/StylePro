"""
Tests for stylepro.editor.server.
Uses urllib.request (stdlib) so no extra deps are needed.
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

import pytest

from stylepro.core.store import JSONThemeStore
from stylepro.core.theme import Theme, ThemeVariable
from stylepro.editor.server import EditorServer


# ---------------------------------------------------------------------------
# Fixture: a running server on an OS-assigned port
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return JSONThemeStore(tmp_path)


@pytest.fixture
def server(store):
    srv = EditorServer(store, host="127.0.0.1", port=0)  # port=0 -> OS picks
    srv.start()
    yield srv
    srv.stop()


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _delete(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _put(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_server_health(server):
    code, body = _get(f"{server.api_url}/health")
    assert code == 200
    assert body["status"] == "ok"


def test_server_list_themes_empty(server):
    code, body = _get(f"{server.api_url}/themes")
    assert code == 200
    assert body["themes"] == []


def test_server_save_theme(server):
    payload = {
        "name": "dark",
        "variables": {
            "--sp-bg": {
                "name": "--sp-bg",
                "value": "#000",
                "label": "BG",
                "category": "color",
                "element_selector": None,
            }
        },
        "metadata": {},
        "role": "admin",
    }
    code, body = _post(f"{server.api_url}/themes", payload)
    assert code == 200
    assert body["status"] == "saved"


def test_server_get_saved_theme(server):
    payload = {
        "name": "light",
        "variables": {
            "--sp-bg": {
                "name": "--sp-bg", "value": "#fff",
                "label": "BG", "category": "color", "element_selector": None,
            }
        },
        "metadata": {},
        "role": "admin",
    }
    _post(f"{server.api_url}/themes", payload)
    code, body = _get(f"{server.api_url}/themes/light")
    assert code == 200
    assert body["name"] == "light"


def test_server_get_unknown_theme_404(server):
    code, body = _get(f"{server.api_url}/themes/ghost")
    assert code == 404


def test_server_list_themes_after_save(server):
    for name in ["alpha", "beta", "gamma"]:
        _post(f"{server.api_url}/themes", {
            "name": name,
            "variables": {},
            "metadata": {},
            "role": "admin",
        })
    code, body = _get(f"{server.api_url}/themes")
    assert code == 200
    assert sorted(body["themes"]) == ["alpha", "beta", "gamma"]


def test_server_rejects_bad_css_value(server):
    payload = {
        "name": "evil",
        "variables": {
            "--sp-bg": {
                "name": "--sp-bg",
                "value": "url(javascript:alert(1))",
                "label": "BG", "category": "color", "element_selector": None,
            }
        },
        "metadata": {},
        "role": "admin",
    }
    code, body = _post(f"{server.api_url}/themes", payload)
    assert code == 400
    assert "error" in body


def test_server_rejects_guest_save(server):
    payload = {
        "name": "attempt",
        "variables": {},
        "metadata": {},
        "role": "guest",
    }
    code, body = _post(f"{server.api_url}/themes", payload)
    assert code == 403


def test_server_activate_theme(server):
    _post(f"{server.api_url}/themes", {
        "name": "dark", "variables": {}, "metadata": {}, "role": "admin",
    })
    code, body = _put(f"{server.api_url}/themes/dark/activate", {"role": "admin"})
    assert code == 200
    assert body["status"] == "activated"


def test_server_activate_unknown_theme_404(server):
    code, body = _put(f"{server.api_url}/themes/ghost/activate", {"role": "admin"})
    assert code == 404


def test_server_delete_theme(server):
    _post(f"{server.api_url}/themes", {
        "name": "todelete", "variables": {}, "metadata": {}, "role": "admin",
    })
    code, body = _delete(f"{server.api_url}/themes/todelete", {"role": "admin"})
    assert code == 200
    assert body["status"] == "deleted"
    # Verify it's gone
    code2, _ = _get(f"{server.api_url}/themes/todelete")
    assert code2 == 404


def test_server_delete_unknown_theme_404(server):
    code, body = _delete(f"{server.api_url}/themes/ghost", {"role": "admin"})
    assert code == 404


def test_server_start_is_idempotent(store):
    srv = EditorServer(store, host="127.0.0.1", port=0)
    srv.start()
    try:
        # Calling start() again must not raise or spawn a second thread.
        srv.start()
        assert srv.is_running()
    finally:
        srv.stop()


def test_server_is_running_after_start(store):
    srv = EditorServer(store, host="127.0.0.1", port=0)
    assert not srv.is_running()
    srv.start()
    assert srv.is_running()
    srv.stop()
