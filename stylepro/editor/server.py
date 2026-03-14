"""
stylepro.editor.server
-----------------------
Lightweight HTTP API server that runs on a background daemon thread.

The browser-side JS editor sends theme changes here; this server
validates, sanitises, and persists them via the ThemeStore.

Routes:
    GET    /health                    -> 200 {"status": "ok"}
    GET    /themes                    -> 200 {"themes": [...names]}
    GET    /themes/{name}             -> 200 theme dict  |  404
    POST   /themes                    -> 200 {"status": "saved"}  |  400  |  403
    PUT    /themes/{name}/activate    -> 200 {"status": "activated"}  |  404  |  403
    DELETE /themes/{name}             -> 200 {"status": "deleted"}  |  404  |  403
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import urlparse

from stylepro.core.permissions import AccessContext, Permission, require_permission
from stylepro.core.store import ThemeStore
from stylepro.core.theme import Theme
from stylepro.utils.css import sanitize_css_value

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """HTTP request handler.  Shares state via server.store / server.config."""

    # Silence the default per-request log line; we use our own logger.
    def log_message(self, fmt: str, *args) -> None:  # noqa: N802
        logger.debug("HTTP %s", fmt % args)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code: int, message: str) -> None:
        self._send_json(code, {"error": message})

    def _add_cors_headers(self) -> None:
        origins = getattr(self.server, "allowed_origins", ["*"])
        origin = "*" if "*" in origins else ", ".join(origins)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-StylePro-Key")

    def _read_json_body(self) -> Optional[dict]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Malformed JSON body: %s", exc)
            return None

    def _parse_role(self, body: Optional[dict]) -> AccessContext:
        """Build an AccessContext from the request body (JS sends role)."""
        from stylepro.core.permissions import Role
        role_str = (body or {}).get("role", "guest")
        try:
            role = Role(role_str)
        except ValueError:
            role = Role.GUEST
        return AccessContext(role=role, user_id=(body or {}).get("user_id"))

    def _path_parts(self) -> list[str]:
        return [p for p in urlparse(self.path).path.split("/") if p]

    # ------------------------------------------------------------------
    # OPTIONS (CORS preflight)
    # ------------------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._add_cors_headers()
        self.end_headers()

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parts = self._path_parts()
        store: ThemeStore = self.server.store

        if not parts or parts == ["health"]:
            self._send_json(200, {"status": "ok", "version": _server_version()})

        elif parts == ["themes"]:
            self._send_json(200, {"themes": store.list_themes()})

        elif len(parts) == 2 and parts[0] == "themes":
            name = parts[1]
            theme = store.load(name)
            if theme is None:
                self._send_error(404, f"Theme '{name}' not found.")
            else:
                self._send_json(200, theme.to_dict())

        elif len(parts) == 3 and parts[0] == "themes" and parts[2] == "export.css":
            # GET /themes/{name}/export.css  — download theme as plain CSS file
            name = parts[1]
            theme = store.load(name)
            if theme is None:
                self._send_error(404, f"Theme '{name}' not found.")
            else:
                css = theme.to_css()
                body = css.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/css; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{name}.css"',
                )
                self._add_cors_headers()
                self.end_headers()
                self.wfile.write(body)
                logger.info("EditorServer: exported CSS for theme '%s'", name)

        else:
            self._send_error(404, f"Unknown route: {self.path}")

    # ------------------------------------------------------------------
    # POST /themes  — save a theme
    # ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        parts = self._path_parts()
        store: ThemeStore = self.server.store

        if parts != ["themes"]:
            self._send_error(404, f"Unknown route: {self.path}")
            return

        body = self._read_json_body()
        if body is None:
            self._send_error(400, "Request body must be valid JSON.")
            return

        ctx = self._parse_role(body)
        try:
            require_permission(ctx, Permission.SAVE_THEME)
        except PermissionError as exc:
            self._send_error(403, str(exc))
            return

        try:
            theme = _theme_from_request(body)
        except (KeyError, ValueError) as exc:
            self._send_error(400, f"Invalid theme data: {exc}")
            return

        store.save(theme)
        logger.info("EditorServer: saved theme '%s' (role=%s)", theme.name, ctx.role.value)
        self._send_json(200, {"status": "saved", "name": theme.name})

    # ------------------------------------------------------------------
    # PUT /themes/{name}/activate
    # ------------------------------------------------------------------

    def do_PUT(self) -> None:  # noqa: N802
        parts = self._path_parts()
        store: ThemeStore = self.server.store

        if len(parts) == 3 and parts[0] == "themes" and parts[2] == "activate":
            name = parts[1]
            body = self._read_json_body() or {}
            ctx = self._parse_role(body)
            try:
                require_permission(ctx, Permission.EDIT_GLOBAL)
            except PermissionError as exc:
                self._send_error(403, str(exc))
                return
            try:
                store.set_active(name)
            except KeyError:
                self._send_error(404, f"Theme '{name}' not found.")
                return
            logger.info("EditorServer: activated theme '%s'", name)
            self._send_json(200, {"status": "activated", "name": name})
        else:
            self._send_error(404, f"Unknown route: {self.path}")

    # ------------------------------------------------------------------
    # DELETE /themes/{name}
    # ------------------------------------------------------------------

    def do_DELETE(self) -> None:  # noqa: N802
        parts = self._path_parts()
        store: ThemeStore = self.server.store

        if len(parts) == 2 and parts[0] == "themes":
            name = parts[1]
            body = self._read_json_body() or {}
            ctx = self._parse_role(body)
            try:
                require_permission(ctx, Permission.DELETE_THEME)
            except PermissionError as exc:
                self._send_error(403, str(exc))
                return
            existed = store.delete(name)
            if not existed:
                self._send_error(404, f"Theme '{name}' not found.")
                return
            logger.info("EditorServer: deleted theme '%s'", name)
            self._send_json(200, {"status": "deleted", "name": name})
        else:
            self._send_error(404, f"Unknown route: {self.path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _server_version() -> str:
    try:
        from importlib.metadata import version
        return version("stylepro")
    except Exception:
        return "unknown"


def _theme_from_request(body: dict) -> Theme:
    """
    Deserialise and sanitise a theme from a POST request body.

    Expected body shape::

        {
            "name": "my_theme",
            "variables": {
                "--sp-bg-color": {
                    "name": "--sp-bg-color",
                    "value": "#ffffff",
                    "label": "Background",
                    "category": "color",
                    "element_selector": null
                },
                ...
            },
            "metadata": {},
            "role": "admin"
        }

    All CSS values are sanitised before the Theme is constructed.
    Raises ValueError or KeyError on invalid input.
    """
    name = body.get("name")
    if not name or not isinstance(name, str):
        raise ValueError("Theme 'name' is required and must be a string.")

    raw_vars = body.get("variables", {})
    if not isinstance(raw_vars, dict):
        raise ValueError("'variables' must be a dict.")

    # Sanitise every CSS value before touching the store.
    for var_name, var_data in raw_vars.items():
        raw_value = var_data.get("value", "")
        var_data["value"] = sanitize_css_value(raw_value)

    return Theme.from_dict({
        "name": name,
        "variables": raw_vars,
        "metadata": body.get("metadata", {}),
    })


# ---------------------------------------------------------------------------
# EditorServer
# ---------------------------------------------------------------------------

class EditorServer:
    """
    Wraps a stdlib HTTPServer in a daemon thread.

    Usage::

        server = EditorServer(store, port=5001)
        server.start()   # non-blocking; daemon thread
        # ... app runs ...
        server.stop()    # optional; daemon thread dies with process anyway
    """

    def __init__(
        self,
        store: ThemeStore,
        host: str = "127.0.0.1",
        port: int = 5001,
        allowed_origins: Optional[list[str]] = None,
        secret_key: Optional[str] = None,
    ):
        self.store = store
        self.host = host
        self.port = port
        self.allowed_origins = allowed_origins or ["*"]
        self.secret_key = secret_key

        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._ready_event = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the HTTP server in a daemon thread.

        Idempotent — calling start() on an already-running server is a no-op.
        Blocks briefly until the socket is bound and ready to accept connections.

        If the requested port is in use, retries on incrementing ports
        (up to 10 attempts). Use port=0 to let the OS assign a free port.
        """
        with self._lock:
            if self.is_running():
                logger.debug("EditorServer.start: already running on %s", self.api_url)
                return

            self._ready_event.clear()
            self._start_error: Optional[Exception] = None

            max_retries = 10 if self.port != 0 else 1
            original_port = self.port

            def _run(port: int):
                try:
                    server = HTTPServer((self.host, port), _Handler)
                except OSError as exc:
                    self._start_error = exc
                    self._ready_event.set()
                    return

                server.store = self.store
                server.allowed_origins = self.allowed_origins
                server.secret_key = self.secret_key
                self._server = server
                # Actual bound port may differ from requested if port=0.
                self.port = server.server_address[1]
                logger.info(
                    "EditorServer: listening on %s (thread=%s)",
                    self.api_url, threading.current_thread().name,
                )
                self._start_error = None
                self._ready_event.set()
                server.serve_forever()

            for attempt in range(max_retries):
                port = original_port + attempt
                self._ready_event.clear()
                self._start_error = None

                self._thread = threading.Thread(
                    target=_run, args=(port,), daemon=True, name="stylepro-api",
                )
                self._thread.start()
                self._ready_event.wait(timeout=5.0)

                if not self._ready_event.is_set():
                    raise RuntimeError(
                        f"EditorServer timed out trying to bind "
                        f"(host={self.host}, port={port})."
                    )

                if self._start_error is None:
                    # Successfully bound.
                    return

                # Bind failed — log and retry on next port.
                logger.warning(
                    "EditorServer: port %d unavailable (%s), trying next...",
                    port, self._start_error,
                )
                self._thread.join(timeout=1.0)
                self._thread = None

            # All retries exhausted.
            raise RuntimeError(
                f"EditorServer could not bind to any port in range "
                f"{original_port}..{original_port + max_retries - 1} "
                f"on {self.host}. Last error: {self._start_error}"
            )

    def stop(self) -> None:
        """Gracefully shut down the server."""
        with self._lock:
            if self._server is not None:
                self._server.shutdown()
                self._server = None
                logger.info("EditorServer: stopped.")
            if self._thread is not None:
                self._thread.join(timeout=3.0)
                self._thread = None

    @property
    def api_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
