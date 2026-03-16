"""
stylepro.integrations.base
---------------------------
Abstract contract every framework integration must satisfy.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class FrameworkIntegration(ABC):
    """
    Base class for all framework-specific StylePro adapters.

    Subclasses implement inject(), get_css_injection_html(), and
    get_editor_html() for their target framework.
    """

    def __init__(
        self,
        store,
        server,
        access_context,
        config: Optional[dict] = None,
    ):
        self.store = store
        self.server = server
        self.access_context = access_context
        self.config = config or {}
        logger.debug(
            "%s created (role=%s, api=%s)",
            type(self).__name__,
            access_context.role.value,
            server.api_url,
        )

    @abstractmethod
    def inject(self) -> None:
        """
        Called once per page render cycle.

        Must:
        1. Load the active theme and generate its CSS.
        2. Inject the CSS into the page.
        3. Inject window.STYLEPRO_CONFIG + editor JS.
        """

    @abstractmethod
    def get_css_injection_html(self, theme) -> str:
        """Return the <style> block for the active theme's CSS variables."""

    @abstractmethod
    def get_editor_html(self) -> str:
        """Return the <script> block containing config + editor JS."""

    # Subclasses set this to identify the framework so the JS can adapt its
    # editor-toggle UI (hamburger menu injection vs floating button).
    # Default is "streamlit" so existing Streamlit behaviour is unchanged
    # unless a subclass explicitly overrides it (e.g. DashStylePro uses "dash").
    _FRAMEWORK: str = "streamlit"

    def _build_js_config(self) -> dict:
        """Assemble the window.STYLEPRO_CONFIG payload from runtime state."""
        active_theme = self.store.get_active()
        return {
            "role": self.access_context.role.value,
            "user_id": self.access_context.user_id,
            "session_id": self.access_context.session_id,
            "api_url": self.server.api_url,
            "theme_name": active_theme.name if active_theme else "default",
            "secret_key": self.server.secret_key,
            "fab_position": self.config.get("fab_position", "bottom-right"),
            "css_var_prefix": self.config.get("css_var_prefix", "--sp"),
            # Tells editor.js which toggle UI to use:
            # "streamlit" → inject into hamburger menu
            # anything else → floating action button (FAB)
            "framework": self._FRAMEWORK,
        }

    def _js_config_script(self) -> str:
        """Return a <script> tag that sets window.STYLEPRO_CONFIG."""
        cfg = self._build_js_config()
        return (
            "<script>\n"
            f"window.STYLEPRO_CONFIG = {json.dumps(cfg, indent=2)};\n"
            "</script>"
        )
