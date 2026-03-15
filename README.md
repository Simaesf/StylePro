# StylePro

A pip-installable Python package that adds a non-intrusive visual style editor overlay to web applications. StylePro lets users visually edit component styles (colors, spacing, typography, borders), resize and reposition elements, and persist themes — all without writing CSS.

**Supported frameworks:** Streamlit (v0.1), Dash (v0.2, planned), Angular (v2, planned)

## Features

- **Canvas edit mode** — click the "StylePro Editor" menu item to activate. The entire page becomes editable: hover any element to see selection highlights, resize handles, and color pickers.
- **Live CSS preview** — changes apply instantly via CSS custom properties. No server round-trip during editing.
- **Per-component targeting** — each element gets a deterministic `data-sp-id` attribute. Style overrides are scoped to individual components without touching app code.
- **Role-based access control** — three roles with different capabilities:
  - **admin**: full editing (colors, layout, resize, move), global save to server
  - **user**: color editing only, personal save to browser localStorage
  - **guest**: view only, editor hidden
- **Undo/redo** — Ctrl+Z / Ctrl+Y with a 200-action stack
- **Pluggable storage** — themes persist via JSON files, YAML files, or SQLite (all thread-safe)
- **Keyboard shortcuts** — Escape (deactivate), Ctrl+S (save), arrow keys (nudge, admin only)
- **Streamlit menu integration** — editor toggle appears in Streamlit's native hamburger menu
- **Rerun resilience** — editor state survives Streamlit reruns via sessionStorage
- **Zero hard dependencies** — stdlib-only core; framework support is opt-in via extras

## Installation

```bash
# Core package (no framework dependencies)
pip install stylepro

# With Streamlit support
pip install 'stylepro[streamlit]'

# With all optional dependencies
pip install 'stylepro[all]'

# Development (editable install with test dependencies)
cd StylePro
pip install -e '.[streamlit,dev]'
```

## Quick Start (Streamlit)

Add three lines to the top of your Streamlit script:

```python
from stylepro import StreamlitStylePro

sp = StreamlitStylePro.from_config(role="admin")
sp.inject()

# ... rest of your Streamlit app ...
import streamlit as st
st.title("My App")
```

Run it:

```bash
streamlit run your_app.py
```

Open the hamburger menu (top-right) and click "StylePro Editor" to activate canvas edit mode.

## Explicit Setup

For more control over storage, server, and permissions:

```python
from stylepro import StreamlitStylePro, JSONThemeStore, SQLiteThemeStore, EditorServer
from stylepro.core.permissions import AccessContext, Role

# Choose a storage backend
store = JSONThemeStore(".my_themes")
# or: store = SQLiteThemeStore(".my_themes/themes.db")

# Configure the API server
server = EditorServer(store, port=5001)

# Set up access control
ctx = AccessContext(role=Role.ADMIN, user_id="alice@example.com")

# Create and inject
sp = StreamlitStylePro(store=store, server=server, access_context=ctx)
sp.inject()
```

## Architecture

```
stylepro/
    __init__.py              # Public API surface (lazy imports for integrations)
    core/
        theme.py             # Theme + ThemeVariable dataclasses
        store.py             # ThemeStore ABC + JSON/YAML/SQLite adapters
        permissions.py       # Role, Permission, AccessContext, ROLE_PERMISSIONS
    editor/
        server.py            # HTTP API daemon thread (6 routes)
        static/
            editor.js        # Vanilla JS canvas editor
            editor.css       # Shadow DOM overlay styles
            color_picker.js  # Standalone HSV color picker widget
    integrations/
        base.py              # FrameworkIntegration ABC
        streamlit.py         # Streamlit adapter
        dash.py              # Dash stub (v0.2)
    utils/
        css.py               # CSS generation + sanitization
tests/
    conftest.py
    test_theme.py
    test_store.py
    test_permissions.py
    test_server.py
    test_css.py
examples/
    streamlit_app.py         # Demo Streamlit app
    dash_app.py              # Demo Dash app (stub)
```

See [docs/architecture.md](docs/architecture.md) for detailed design decisions and component descriptions.

## API Reference

See [docs/api.md](docs/api.md) for the full API reference covering all public classes and functions.

### Key Classes

| Class | Module | Description |
|-------|--------|-------------|
| `Theme` | `stylepro.core.theme` | Named collection of CSS variables with serialization and merge support |
| `ThemeVariable` | `stylepro.core.theme` | Single CSS custom property entry |
| `ThemeStore` | `stylepro.core.store` | Abstract interface for theme persistence |
| `JSONThemeStore` | `stylepro.core.store` | JSON file-based storage adapter |
| `SQLiteThemeStore` | `stylepro.core.store` | SQLite-based storage adapter |
| `YAMLThemeStore` | `stylepro.core.store` | YAML file-based storage (requires PyYAML) |
| `Role` | `stylepro.core.permissions` | Enum: ADMIN, USER, GUEST |
| `Permission` | `stylepro.core.permissions` | Enum: EDIT_GLOBAL, EDIT_PERSONAL, SAVE_THEME, DELETE_THEME, VIEW_EDITOR |
| `AccessContext` | `stylepro.core.permissions` | Carries role and user identity |
| `EditorServer` | `stylepro.editor.server` | Background HTTP API server for theme CRUD |
| `StreamlitStylePro` | `stylepro.integrations.streamlit` | Streamlit framework adapter |

### HTTP API Routes

The `EditorServer` exposes these routes (default: `http://127.0.0.1:5001`):

| Method | Path | Description | Required Permission |
|--------|------|-------------|-------------------|
| GET | `/health` | Health check | None |
| GET | `/themes` | List all theme names | None |
| GET | `/themes/{name}` | Get theme by name | None |
| POST | `/themes` | Save a theme | SAVE_THEME (admin only) |
| PUT | `/themes/{name}/activate` | Set active theme | EDIT_GLOBAL (admin only) |
| DELETE | `/themes/{name}` | Delete a theme | DELETE_THEME (admin only) |

## Role Permissions

| Permission | Admin | User | Guest |
|------------|-------|------|-------|
| EDIT_GLOBAL (layout, resize, move) | Yes | No | No |
| EDIT_PERSONAL (colors) | Yes | Yes | No |
| SAVE_THEME (global server save) | Yes | No | No |
| DELETE_THEME | Yes | No | No |
| VIEW_EDITOR | Yes | Yes | No |

**User-role save behavior:** Users can edit colors and save changes to their browser's localStorage. These personal themes load automatically on return visits but do not affect other users.

## Storage Backends

### JSONThemeStore (default)

Stores themes as individual JSON files:

```
.stylepro/
    themes/
        my_theme.json
        dark.json
    active.txt          # contains the active theme name
```

### SQLiteThemeStore

Single-file database using stdlib sqlite3:

```python
store = SQLiteThemeStore(".stylepro/themes.db")
```

### YAMLThemeStore

Requires PyYAML (`pip install 'stylepro[yaml]'`):

```python
store = YAMLThemeStore(".stylepro")
```

All adapters are thread-safe (RLock for file-based, WAL mode for SQLite).

## CSS Security

All CSS values submitted through the API are sanitized by `stylepro.utils.css.sanitize_css_value()` before storage. The following constructs are blocked:

- `url()`, `expression()`, `javascript:`, `vbscript:`, `data:`
- `@import`, `<script>`, `behavior:`, `-moz-binding`

Values must match a safe-value allowlist (hex colors, rgb/hsl functions, numbers with units, safe CSS keywords, calc(), var()).

## Testing

```bash
cd StylePro
pip install -e '.[dev]'
pytest
```

Current status: 74 tests passing, 2 skipped (YAML tests when PyYAML is not installed).

## Configuration

`StreamlitStylePro.from_config()` accepts these parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `store` | `ThemeStore` | `JSONThemeStore('.stylepro')` | Storage backend |
| `role` | `str` or `Role` | `'guest'` | User role |
| `user_id` | `str` | `None` | Optional user identifier |
| `api_port` | `int` | `5001` | API server port (0 = OS-assigned) |
| `config` | `dict` | `None` | Extra config (fab_position, css_var_prefix) |

The API server auto-retries on incrementing ports (up to 10 attempts) if the requested port is in use.

## Keyboard Shortcuts (in edit mode)

| Shortcut | Action | Role Required |
|----------|--------|--------------|
| Escape | Deactivate edit mode | Any |
| Ctrl+Z | Undo | Any |
| Ctrl+Y | Redo | Any |
| Ctrl+S | Save | User or Admin |
| Arrow keys | Nudge element 1px | Admin |
| Shift+Arrow keys | Nudge element 10px | Admin |

## Development Status

- **v0.1.0.dev0** (current) — Streamlit integration, core data model, storage, API server, JS editor
- **v0.2.0** (planned) — Dash integration
- **v2.0.0** (planned) — Angular support

## License

MIT
