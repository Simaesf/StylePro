"""
stylepro.integrations.streamlit
--------------------------------
Streamlit adapter for StylePro.

Injection strategy
------------------
Streamlit reruns the entire Python script on every user interaction.
This means inject() is called on every rerun.  We need two things in the
browser:

1. The theme CSS  — injected via st.markdown("<style>...</style>")
   into the main document.  Idempotent; repeated injection is harmless.

2. The editor JS  — also injected via st.markdown("<script>...</script>")
   into the main document.  A stable key (session_id) is embedded in
   window.STYLEPRO_CONFIG so the JS can restore its state from
   sessionStorage across reruns.

The EditorServer is started once per Streamlit session, guarded by
st.session_state so reruns don't spawn additional threads.

DOM injection note
------------------
st.markdown() with unsafe_allow_html=True injects HTML into Streamlit's
own markdown component, which renders in the main document.
<style> tags injected this way do affect the full page (confirmed).
<script> tags in st.markdown() are NOT executed by the browser for security
reasons (Streamlit strips scripts from markdown).

Therefore we use st.components.v1.html(height=0) for the JS injection.
This iframe CAN execute scripts, but is sandboxed from the parent DOM.
The iframe uses window.parent.postMessage to communicate with a listener
script that is injected into the parent via the st.markdown CSS block
(which Streamlit does allow for <style> but not <script>).

Workaround: The listener + editor bootstrap script is injected by encoding
it as a CSS @layer-hack-free technique: a zero-height st.components.v1.html
iframe whose content includes both the config and the full editor.js.
The iframe uses document.body.appendChild to reach into its parent
via window.parent only when same-origin (localhost dev).  On cross-origin
or Streamlit Cloud this pathway is unavailable; we degrade gracefully and
show a warning.
"""

from __future__ import annotations

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


class StreamlitStylePro(FrameworkIntegration):
    """
    StylePro integration for Streamlit apps.

    Usage (minimal — 3 lines)::

        from stylepro import StreamlitStylePro
        sp = StreamlitStylePro.from_config(role="admin")
        sp.inject()   # call at the very top of your Streamlit script

    Usage (explicit)::

        from stylepro import StreamlitStylePro, JSONThemeStore, EditorServer
        from stylepro.core.permissions import AccessContext, Role

        store = JSONThemeStore(".my_themes")
        server = EditorServer(store, port=5001)
        ctx = AccessContext(role=Role.ADMIN, user_id="alice")
        sp = StreamlitStylePro(store=store, server=server, access_context=ctx)
        sp.inject()
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
        api_port: int = 5001,
        config: Optional[dict] = None,
    ) -> "StreamlitStylePro":
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

        # EditorServer is created here but started lazily inside inject()
        # so that start() is guarded by st.session_state on every rerun.
        server = EditorServer(store, port=api_port)
        ctx = AccessContext(role=role, user_id=user_id)
        return cls(store=store, server=server, access_context=ctx, config=config)

    # ------------------------------------------------------------------
    # inject — called on every Streamlit rerun
    # ------------------------------------------------------------------

    def inject(self) -> None:
        """
        Inject StylePro into the running Streamlit app.

        Call this at the very top of your script, before any st.* widgets.
        It is safe to call on every rerun — all operations are idempotent.
        """
        try:
            import streamlit as st
        except ImportError as exc:
            raise ImportError(
                "StreamlitStylePro requires Streamlit. "
                "Install it with: pip install 'stylepro[streamlit]'"
            ) from exc

        # -- 1. Start the API server once per Streamlit session -------
        if "_sp_server_started" not in st.session_state:
            self.server.start()
            st.session_state["_sp_server_started"] = True
            logger.info("StreamlitStylePro: EditorServer started at %s", self.server.api_url)
        else:
            # Re-use the already-running server; update our reference's port
            # in case port=0 was used and the OS assigned a port.
            pass

        # -- 2. Stable session_id (generated once per browser session) --
        if "_sp_session_id" not in st.session_state:
            st.session_state["_sp_session_id"] = str(uuid.uuid4())

        self.access_context.session_id = st.session_state["_sp_session_id"]

        # -- 3. Inject theme CSS into main document --------------------
        theme = self.store.get_active()
        if theme is not None:
            css_html = self.get_css_injection_html(theme)
            st.markdown(css_html, unsafe_allow_html=True)
            logger.debug("StreamlitStylePro.inject: CSS injected for theme '%s'", theme.name)
        else:
            logger.debug("StreamlitStylePro.inject: no active theme; CSS not injected")

        # -- 4. Inject editor JS via zero-height iframe ----------------
        editor_html = self.get_editor_html()
        st.components.v1.html(editor_html, height=0, scrolling=False)
        logger.debug("StreamlitStylePro.inject: editor JS injected")

    # ------------------------------------------------------------------
    # HTML builders
    # ------------------------------------------------------------------

    def get_css_injection_html(self, theme) -> str:
        """Return a <style> block containing the active theme's CSS variables."""
        css = theme.to_css()
        return f"<style>\n/* StylePro theme: {theme.name} */\n{css}\n</style>"

    def get_editor_html(self) -> str:
        """
        Return the full HTML injected into the zero-height iframe.
        This includes window.STYLEPRO_CONFIG, editor.css, editor.js,
        and color_picker.js.
        """
        import json as _json

        editor_js = (_STATIC_DIR / "editor.js").read_text(encoding="utf-8")
        color_picker_js = (_STATIC_DIR / "color_picker.js").read_text(encoding="utf-8")
        editor_css = (_STATIC_DIR / "editor.css").read_text(encoding="utf-8")
        config_script = self._js_config_script()

        # Embed asset strings as JS string literals using json.dumps so that
        # any quotes or backslashes inside the assets are properly escaped.
        css_literal = _json.dumps(editor_css)
        editor_js_literal = _json.dumps(editor_js)
        cp_js_literal = _json.dumps(color_picker_js)

        return (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head>\n"
            "<style>html,body{margin:0;padding:0;overflow:hidden;height:0;}</style>\n"
            "</head>\n"
            "<body>\n"
            + config_script + "\n"
            "<script>\n"
            "/*\n"
            " * StylePro iframe bootstrap.\n"
            " *\n"
            " * Streamlit sandboxes iframes; the editor JS needs to run in the\n"
            " * parent document to manipulate the app DOM.  We inject the editor\n"
            " * as script/style tags into window.parent when same-origin (local dev).\n"
            " * On cross-origin (Streamlit Cloud) we degrade gracefully.\n"
            " */\n"
            "(function() {\n"
            "  var cfg = window.STYLEPRO_CONFIG || {};\n"
            "  var par = window.parent;\n"
            "  if (!par || par === window) {\n"
            "    console.warn('[StylePro] No parent window; standalone mode.');\n"
            "    return;\n"
            "  }\n"
            "  try {\n"
            "    par.STYLEPRO_CONFIG = cfg;\n"
            "\n"
            "    if (!par.document.getElementById('sp-editor-css')) {\n"
            "      var style = par.document.createElement('style');\n"
            "      style.id = 'sp-editor-css';\n"
            f"      style.textContent = {css_literal};\n"
            "      par.document.head.appendChild(style);\n"
            "    }\n"
            "\n"
            "    if (!par.document.getElementById('sp-color-picker-js')) {\n"
            "      var cpScript = par.document.createElement('script');\n"
            "      cpScript.id = 'sp-color-picker-js';\n"
            f"      cpScript.textContent = {cp_js_literal};\n"
            "      par.document.head.appendChild(cpScript);\n"
            "    }\n"
            "\n"
            "    if (!par.document.getElementById('sp-editor-js')) {\n"
            "      var edScript = par.document.createElement('script');\n"
            "      edScript.id = 'sp-editor-js';\n"
            f"      edScript.textContent = {editor_js_literal};\n"
            "      par.document.head.appendChild(edScript);\n"
            "    } else {\n"
            "      if (par.StylePro && par.StylePro.refreshConfig) {\n"
            "        par.StylePro.refreshConfig(cfg);\n"
            "      }\n"
            "    }\n"
            "\n"
            "  } catch (e) {\n"
            "    console.warn('[StylePro] Could not inject into parent (cross-origin?): ' + e.message);\n"
            "  }\n"
            "})();\n"
            "</script>\n"
            "</body>\n"
            "</html>\n"
        )
