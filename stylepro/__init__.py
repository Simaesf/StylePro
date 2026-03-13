"""
stylepro — visual style editor overlay for web applications.

Quickstart (Streamlit):
    from stylepro import StreamlitStylePro
    sp = StreamlitStylePro.from_config(role="admin")
    sp.inject()
"""

__version__ = "0.1.0.dev0"

from stylepro.core.theme import Theme, ThemeVariable
from stylepro.core.store import ThemeStore, JSONThemeStore, SQLiteThemeStore
from stylepro.core.permissions import Role, Permission, AccessContext
from stylepro.editor.server import EditorServer

# Framework integrations — imported lazily to avoid hard dependency errors
# when the optional package (streamlit / dash) is not installed.

def _lazy_streamlit():
    from stylepro.integrations.streamlit import StreamlitStylePro
    return StreamlitStylePro

def _lazy_dash():
    from stylepro.integrations.dash import DashStylePro
    return DashStylePro


__all__ = [
    "__version__",
    # Core
    "Theme",
    "ThemeVariable",
    "ThemeStore",
    "JSONThemeStore",
    "SQLiteThemeStore",
    "Role",
    "Permission",
    "AccessContext",
    "EditorServer",
    # Integrations (accessed via lazy helpers or direct import)
    "StreamlitStylePro",
    "DashStylePro",
]

# Expose integration classes at package level via __getattr__ so that
# importing a missing optional dependency raises a clear error only when
# the class is actually used, not on 'import stylepro'.
def __getattr__(name: str):
    if name == "StreamlitStylePro":
        return _lazy_streamlit()
    if name == "DashStylePro":
        return _lazy_dash()
    raise AttributeError(f"module 'stylepro' has no attribute {name!r}")
