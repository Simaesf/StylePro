# StylePro API Reference

## Package: `stylepro`

### Top-Level Imports

```python
from stylepro import (
    Theme, ThemeVariable,
    ThemeStore, JSONThemeStore, SQLiteThemeStore,
    Role, Permission, AccessContext,
    EditorServer,
    StreamlitStylePro,  # lazy import, requires streamlit
)
```

---

## `stylepro.core.theme`

### `ThemeVariable`

A single CSS custom-property entry within a theme.

```python
@dataclass
class ThemeVariable:
    name: str                           # CSS variable name, e.g. "--sp-bg-color"
    value: str                          # CSS value string, e.g. "#ffffff"
    label: str                          # Human-readable label for the editor UI
    category: str                       # "color", "spacing", "typography", or "border"
    element_selector: Optional[str]     # Per-component selector or None (global)
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Serialize to JSON-compatible dict |
| `from_dict(data)` | `ThemeVariable` | Class method; deserialize from dict |

### `Theme`

A named collection of `ThemeVariable` entries.

```python
@dataclass
class Theme:
    name: str
    variables: dict[str, ThemeVariable]  # keyed by variable name
    metadata: dict[str, str]             # arbitrary key/value pairs
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_css()` | `str` | Render as CSS string with `:root {}` and per-element blocks |
| `to_dict()` | `dict` | Serialize to JSON-compatible dict |
| `from_dict(data)` | `Theme` | Class method; deserialize from dict |
| `merge(other)` | `Theme` | Immutable union; `other` wins on variable name conflicts |
| `apply_patch(patch)` | `Theme` | Immutable update; `patch` maps var name to new value |

---

## `stylepro.core.store`

### `ThemeStore` (ABC)

Abstract interface for theme persistence. All implementations must be thread-safe.

| Method | Signature | Description |
|--------|-----------|-------------|
| `save` | `(theme: Theme) -> None` | Persist theme, overwriting any existing with same name |
| `load` | `(name: str) -> Optional[Theme]` | Load theme by name, or None if not found |
| `list_themes` | `() -> list[str]` | Sorted list of all stored theme names |
| `delete` | `(name: str) -> bool` | Delete theme; returns True if it existed |
| `get_active` | `() -> Optional[Theme]` | Return the currently active theme |
| `set_active` | `(name: str) -> None` | Mark theme as active; raises `KeyError` if not found |

### `JSONThemeStore`

```python
store = JSONThemeStore(directory=".stylepro")
```

Stores themes as individual JSON files under `{directory}/themes/`. Active theme tracked in `{directory}/active.txt`. Thread-safe via `threading.RLock`.

### `SQLiteThemeStore`

```python
store = SQLiteThemeStore(db_path=".stylepro/themes.db")
```

Single SQLite database with WAL journal mode. Thread-safe via `threading.RLock` + SQLite isolation. No external dependencies (stdlib `sqlite3`).

### `YAMLThemeStore`

```python
store = YAMLThemeStore(directory=".stylepro")
```

Requires PyYAML: `pip install 'stylepro[yaml]'`. Raises `ImportError` with clear message if PyYAML is missing. Same directory layout as `JSONThemeStore` but with `.yaml` extension.

---

## `stylepro.core.permissions`

### `Role` (Enum)

```python
class Role(str, Enum):
    ADMIN = "admin"    # Full access: edit global themes, save, delete
    USER  = "user"     # Can edit colors; saves to browser localStorage only
    GUEST = "guest"    # View only; editor hidden
```

### `Permission` (Enum)

```python
class Permission(str, Enum):
    EDIT_GLOBAL    = "edit_global"      # Layout editing (resize, move, nudge)
    EDIT_PERSONAL  = "edit_personal"    # Color editing
    SAVE_THEME     = "save_theme"       # Global save to server
    DELETE_THEME   = "delete_theme"     # Delete themes from server
    VIEW_EDITOR    = "view_editor"      # See the editor UI
```

### `ROLE_PERMISSIONS`

```python
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {EDIT_GLOBAL, EDIT_PERSONAL, SAVE_THEME, DELETE_THEME, VIEW_EDITOR},
    Role.USER:  {EDIT_PERSONAL, VIEW_EDITOR},
    Role.GUEST: set(),
}
```

Module-level and mutable. Callers can extend it:

```python
from stylepro.core.permissions import ROLE_PERMISSIONS, Role, Permission
ROLE_PERMISSIONS[Role.USER].add(Permission.SAVE_THEME)  # grant server save to users
```

### `AccessContext`

```python
@dataclass
class AccessContext:
    role: Role
    user_id: Optional[str] = None
    session_id: Optional[str] = None
```

### Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `check_permission` | `(ctx: AccessContext, permission: Permission) -> bool` | Returns True if role holds permission |
| `require_permission` | `(ctx: AccessContext, permission: Permission) -> None` | Raises `PermissionError` if not authorized |

---

## `stylepro.editor.server`

### `EditorServer`

Background HTTP API server running on a daemon thread.

```python
server = EditorServer(
    store: ThemeStore,
    host: str = "127.0.0.1",
    port: int = 5001,
    allowed_origins: Optional[list[str]] = None,  # default: ["*"]
    secret_key: Optional[str] = None,
)
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `start` | `() -> None` | Idempotent; starts daemon thread. Auto-retries ports on bind failure |
| `stop` | `() -> None` | Graceful shutdown |
| `is_running` | `() -> bool` | Check if server thread is alive |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `api_url` | `str` | `"http://{host}:{port}"` |

---

## `stylepro.integrations.streamlit`

### `StreamlitStylePro`

```python
class StreamlitStylePro(FrameworkIntegration):
    ...
```

**Factory:**

```python
sp = StreamlitStylePro.from_config(
    store: Optional[ThemeStore] = None,     # default: JSONThemeStore('.stylepro')
    role: str | Role = "guest",
    user_id: Optional[str] = None,
    api_port: int = 5001,                   # 0 = OS-assigned
    config: Optional[dict] = None,          # extra JS config
)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `inject()` | Call at top of Streamlit script. Starts server, injects CSS + JS. Idempotent across reruns. |
| `get_css_injection_html(theme)` | Returns `<style>` block for the theme's CSS variables |
| `get_editor_html()` | Returns full iframe HTML with config + editor.js + color_picker.js |

---

## `stylepro.utils.css`

### Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `sanitize_css_value` | `(value: str) -> str` | Security gate; raises `ValueError` on dangerous constructs |
| `sanitize_variable_name` | `(name: str, prefix: str = "--sp") -> str` | Enforce prefix, strip bad chars; raises `ValueError` on invalid |
| `variables_to_css_block` | `(selector: str, variables: dict[str, str]) -> str` | Render one CSS rule block |
| `theme_to_css` | `(theme: Theme) -> str` | Full CSS: `:root {}` for globals, scoped blocks for elements |
| `merge_css_blocks` | `(blocks: list[str]) -> str` | Parse and deduplicate CSS blocks; later wins on conflicts |

---

## `stylepro.integrations.base`

### `FrameworkIntegration` (ABC)

Base class for all framework adapters. Subclasses must implement:

- `inject() -> None`
- `get_css_injection_html(theme) -> str`
- `get_editor_html() -> str`

Provided methods:

- `_build_js_config() -> dict` — assembles `window.STYLEPRO_CONFIG`
- `_js_config_script() -> str` — returns `<script>` tag setting the config
