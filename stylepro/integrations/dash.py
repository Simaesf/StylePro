"""
stylepro.integrations.dash
---------------------------
Dash adapter stub.  Full implementation in StylePro v0.2.0.
"""

from __future__ import annotations

import logging

from stylepro.integrations.base import FrameworkIntegration

logger = logging.getLogger(__name__)


class DashStylePro(FrameworkIntegration):
    """
    StylePro integration for Dash apps.

    Available in StylePro v0.2.0.

    Planned injection approach:
    - Use app.index_string to inject CSS/JS into the main HTML template.
    - Register a clientside_callback for live CSS variable preview.
    - Use a dcc.Store component for session state across callbacks.
    """

    _NOT_IMPLEMENTED_MSG = (
        "Dash integration is available in StylePro v0.2.0. "
        "Install with: pip install 'stylepro[dash]'"
    )

    def inject(self) -> None:
        raise NotImplementedError(self._NOT_IMPLEMENTED_MSG)

    def get_css_injection_html(self, theme) -> str:
        raise NotImplementedError(self._NOT_IMPLEMENTED_MSG)

    def get_editor_html(self) -> str:
        raise NotImplementedError(self._NOT_IMPLEMENTED_MSG)
