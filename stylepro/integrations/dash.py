"""
stylepro.integrations.dash
---------------------------
Dash adapter for StylePro.

Injection strategy
------------------
Dash apps have a persistent server process — unlike Streamlit there is no
per-interaction Python rerun.  inject() is called ONCE after the Dash app
object is created and before app.run_server().  It wires up StylePro
permanently via three mechanisms:

1. Flask routes on Dash's underlying Flask server:
   - GET /stylepro/editor.js  — returns color_picker.js + editor.js with
     window.STYLEPRO_CONFIG embedded.  Computed fresh on each request so
     the active theme name is always current.  Cache-Control: no-cache.
   - GET /stylepro/theme.css  — returns the active theme's CSS variables.
     Reloaded on each full page request so a newly saved theme is reflected
     on next browser reload.

2. app.index_string patching — Dash's HTML template is modified to include:
   - <link rel="stylesheet" href="/stylepro/theme.css"> before Dash's {%css%}
   - <script src="/stylepro/editor.js"></script> after Dash's {%scripts%}

3. Session ID — a stable UUID is stored in the Flask session so the JS
   can key sessionStorage correctly across navigations.

Idempotency
-----------
inject() is safe to call multiple times; a guard flag on the Dash app
object prevents double-registration of routes and double-patching of
index_string.

Dependency guard
----------------
Dash and Flask are optional.  Both are imported inside inject() and the
helper methods; a clear ImportError is raised if they are absent.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from stylepro.core.permissions import AccessContext, Role
from stylepro.core.store import JSONThemeStore, ThemeStore
from stylepro.editor.server import EditorServer
from stylepro.integrations.base import FrameworkIntegration

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent.parent / "editor" / "static"

# Sentinel attribute we attach to the Dash app to prevent double-injection.
_INJECTED_ATTR = "_stylepro_injected"


class DashStylePro(FrameworkIntegration):
    """
    StylePro integration for Dash apps.

    Usage (minimal — 3 lines)::

        from stylepro import DashStylePro
        import dash

        app = dash.Dash(__name__)
        sp = DashStylePro.from_config(role="admin")
        sp.inject(app)   # call once, after creating the Dash app

        # ... define layout and callbacks ...
        app.run(debug=True)

    Usage (explicit)::

        from stylepro import DashStylePro, JSONThemeStore, EditorServer
        from stylepro.core.permissions import AccessContext, Role

        store = JSONThemeStore(".my_themes")
        server = EditorServer(store, port=5001)
        ctx = AccessContext(role=Role.ADMIN, user_id="alice")
        sp = DashStylePro(store=store, server=server, access_context=ctx)
        sp.inject(app)
    """

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        store: Optional[ThemeStore] = None,
        role: str | Role = "guest",
        user_id: Optional[str] = None,
        api_port: int = 0,
        config: Optional[dict] = None,
    ) -> "DashStylePro":
        """
        Convenience factory with sensible defaults.

        Parameters
        ----------
        store:
            A ThemeStore instance.  Defaults to JSONThemeStore('.stylepro').
        role:
            'admin', 'user', or 'guest'.
        user_id:
            Optional identifier for the current user.
        api_port:
            Port for the background EditorServer (0 = OS-assigned).
        config:
            Extra config forwarded to window.STYLEPRO_CONFIG
            (fab_position, css_var_prefix, etc.).
        """
        if store is None:
            store = JSONThemeStore(".stylepro")
            logger.debug("from_config: using default JSONThemeStore('.stylepro')")

        if isinstance(role, str):
            try:
                role = Role(role)
            except ValueError:
                logger.warning(
                    "from_config: unknown role '%s', falling back to GUEST", role
                )
                role = Role.GUEST

        server = EditorServer(store, port=api_port)
        ctx = AccessContext(role=role, user_id=user_id)
        return cls(store=store, server=server, access_context=ctx, config=config)

    # ------------------------------------------------------------------
    # inject — called once after creating the Dash app
    # ------------------------------------------------------------------

    def inject(self, app) -> None:
        """
        Inject StylePro into a Dash app.

        Call this once after creating the Dash app object, before calling
        app.run() or app.run_server().  It is idempotent — safe to call
        multiple times on the same app instance.

        Parameters
        ----------
        app : dash.Dash
            The Dash application instance to inject into.

        Raises
        ------
        ImportError
            If dash or flask is not installed.
        """
        try:
            import dash as _dash  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "DashStylePro requires Dash. "
                "Install it with: pip install 'stylepro[dash]'"
            ) from exc

        if getattr(app, _INJECTED_ATTR, False):
            logger.debug("DashStylePro.inject: already injected into this app, skipping")
            return

        # 1. Start the EditorServer (idempotent — EditorServer.start() is guarded).
        self.server.start()
        logger.info("DashStylePro: EditorServer started at %s", self.server.api_url)

        # 2. Generate a stable session_id for this process lifetime.
        #    Unlike Streamlit, Dash does not have per-session Python state,
        #    so we use a single UUID per DashStylePro instance.  The JS can
        #    additionally use its own sessionStorage UUID if needed.
        if not self.access_context.session_id:
            self.access_context.session_id = str(uuid.uuid4())

        # 3. Register Flask routes for editor JS and theme CSS.
        self._register_flask_routes(app.server)

        # 4. Patch the Dash HTML template to load the editor.
        self._patch_index_string(app)

        # Mark as injected to prevent double-injection.
        setattr(app, _INJECTED_ATTR, True)
        logger.info("DashStylePro.inject: injection complete")

    # ------------------------------------------------------------------
    # Flask route registration
    # ------------------------------------------------------------------

    def _register_flask_routes(self, flask_server) -> None:
        """
        Register /stylepro/editor.js and /stylepro/theme.css on the Flask
        server underlying the Dash app.

        Both routes are computed fresh on each request:
        - editor.js: config (including api_url) is stable post-start, but
          computing fresh is cheap and keeps the route simple.
        - theme.css: re-reads the active theme so a newly saved theme is
          reflected on the next full page load without restarting the server.

        Parameters
        ----------
        flask_server : flask.Flask
            The Flask app instance (dash.Dash.server).
        """
        try:
            from flask import Response
        except ImportError as exc:
            raise ImportError(
                "DashStylePro requires Flask (included with Dash). "
                "Install it with: pip install 'stylepro[dash]'"
            ) from exc

        store = self.store
        build_config = self._build_js_config  # bound method reference

        @flask_server.route("/stylepro/editor.js")
        def serve_editor_js():
            """Serve color_picker.js + editor.js with window.STYLEPRO_CONFIG embedded."""
            config_json = json.dumps(build_config(), indent=2)
            color_picker_js = (_STATIC_DIR / "color_picker.js").read_text(encoding="utf-8")
            editor_js = (_STATIC_DIR / "editor.js").read_text(encoding="utf-8")
            js = (
                "/* StylePro — auto-generated, do not edit */\n"
                "window.STYLEPRO_CONFIG = " + config_json + ";\n\n"
                + color_picker_js + "\n\n"
                + editor_js + "\n"
            )
            logger.debug("serve_editor_js: serving editor bundle (%d bytes)", len(js))
            return Response(
                js,
                mimetype="application/javascript",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        @flask_server.route("/stylepro/theme.css")
        def serve_theme_css():
            """Serve the active theme's CSS custom properties."""
            theme = store.get_active()
            if theme is not None:
                css = (
                    "/* StylePro theme: " + theme.name + " */\n"
                    + theme.to_css()
                )
                logger.debug("serve_theme_css: serving theme '%s'", theme.name)
            else:
                css = "/* StylePro: no active theme */\n"
                logger.debug("serve_theme_css: no active theme")
            return Response(
                css,
                mimetype="text/css",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        logger.debug("DashStylePro: Flask routes /stylepro/editor.js and /stylepro/theme.css registered")

    # ------------------------------------------------------------------
    # index_string patching
    # ------------------------------------------------------------------

    def _patch_index_string(self, app) -> None:
        """
        Modify Dash's HTML index template to load the StylePro CSS and JS.

        Dash's default index_string contains {%css%} and {%scripts%}
        placeholders.  We inject:
          - A <link> to /stylepro/theme.css before {%css%} so theme
            variables are available before Dash's own stylesheets.
          - A <script src="/stylepro/editor.js"> after {%scripts%} so
            the editor loads after Dash's React bundle.

        Parameters
        ----------
        app : dash.Dash
            The Dash application instance whose index_string will be modified.
        """
        index = app.index_string

        theme_link = (
            '<link rel="stylesheet" href="/stylepro/theme.css" '
            'id="sp-theme-css">'
        )
        editor_script = (
            '<script src="/stylepro/editor.js" id="sp-editor-js"></script>'
        )

        # Inject theme CSS before Dash's {%css%} placeholder.
        if "{%css%}" in index:
            index = index.replace(
                "{%css%}",
                theme_link + "\n        {%css%}",
                1,
            )
        else:
            logger.warning(
                "DashStylePro._patch_index_string: {%%css%%} placeholder not found "
                "in app.index_string; theme CSS not injected"
            )

        # Inject editor script after Dash's {%scripts%} placeholder.
        if "{%scripts%}" in index:
            index = index.replace(
                "{%scripts%}",
                "{%scripts%}\n        " + editor_script,
                1,
            )
        else:
            logger.warning(
                "DashStylePro._patch_index_string: {%%scripts%%} placeholder not found "
                "in app.index_string; editor JS not injected"
            )

        app.index_string = index
        logger.debug("DashStylePro._patch_index_string: index_string patched")

    # ------------------------------------------------------------------
    # HTML builder stubs — satisfy the abstract interface
    # ------------------------------------------------------------------

    def get_css_injection_html(self, theme) -> str:
        """
        Return a <link> tag pointing to the dynamic theme CSS route.

        In the Dash integration, theme CSS is served via a Flask route rather
        than inlined into the page, so this method returns a link tag instead
        of an inline <style> block.
        """
        return '<link rel="stylesheet" href="/stylepro/theme.css" id="sp-theme-css">'

    def get_editor_html(self) -> str:
        """
        Return a <script> tag pointing to the dynamic editor JS route.

        In the Dash integration, editor JS (including window.STYLEPRO_CONFIG)
        is served via a Flask route rather than inlined into the page.
        """
        return '<script src="/stylepro/editor.js" id="sp-editor-js"></script>'
