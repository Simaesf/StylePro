"""
stylepro.core.store
--------------------
Pluggable theme persistence layer.

All adapters are thread-safe: the EditorServer runs on a background daemon
thread and may call these methods concurrently with the main application.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from stylepro.core.theme import Theme

logger = logging.getLogger(__name__)

_ACTIVE_FILENAME = "active.txt"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class ThemeStore(ABC):
    """
    Abstract interface for theme persistence.

    Implementations must be thread-safe.
    """

    @abstractmethod
    def save(self, theme: Theme) -> None:
        """Persist *theme*, overwriting any existing theme with the same name."""

    @abstractmethod
    def load(self, name: str) -> Optional[Theme]:
        """Load and return the theme called *name*, or None if not found."""

    @abstractmethod
    def list_themes(self) -> list[str]:
        """Return a sorted list of all stored theme names."""

    @abstractmethod
    def delete(self, name: str) -> bool:
        """Delete *name*. Return True if it existed, False otherwise."""

    @abstractmethod
    def get_active(self) -> Optional[Theme]:
        """Return the currently active theme, or None if none is set."""

    @abstractmethod
    def set_active(self, name: str) -> None:
        """Mark *name* as the active theme. Raises KeyError if not found."""


# ---------------------------------------------------------------------------
# JSON adapter
# ---------------------------------------------------------------------------

class JSONThemeStore(ThemeStore):
    """
    Stores themes as JSON files under a local directory.

    Layout::

        {directory}/
            themes/
                my_theme.json
                dark.json
            active.txt       <- contains the active theme name

    Thread-safe via a per-instance reentrant lock.
    """

    def __init__(self, directory: str | Path = ".stylepro"):
        self._dir = Path(directory)
        self._themes_dir = self._dir / "themes"
        self._active_file = self._dir / _ACTIVE_FILENAME
        self._lock = threading.RLock()
        self._ensure_dirs()
        logger.info("JSONThemeStore initialised at '%s'", self._dir)

    def _ensure_dirs(self) -> None:
        self._themes_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        return self._themes_dir / f"{name}.json"

    # ------------------------------------------------------------------

    def save(self, theme: Theme) -> None:
        with self._lock:
            path = self._path_for(theme.name)
            path.write_text(json.dumps(theme.to_dict(), indent=2), encoding="utf-8")
            logger.debug("JSONThemeStore.save: wrote '%s'", path)

    def load(self, name: str) -> Optional[Theme]:
        with self._lock:
            path = self._path_for(name)
            if not path.exists():
                logger.debug("JSONThemeStore.load: '%s' not found", name)
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            theme = Theme.from_dict(data)
            logger.debug("JSONThemeStore.load: loaded '%s'", name)
            return theme

    def list_themes(self) -> list[str]:
        with self._lock:
            names = sorted(p.stem for p in self._themes_dir.glob("*.json"))
            logger.debug("JSONThemeStore.list_themes: %s", names)
            return names

    def delete(self, name: str) -> bool:
        with self._lock:
            path = self._path_for(name)
            if not path.exists():
                return False
            path.unlink()
            # Clear active pointer if we just deleted the active theme.
            if self._active_file.exists():
                if self._active_file.read_text(encoding="utf-8").strip() == name:
                    self._active_file.unlink()
            logger.info("JSONThemeStore.delete: removed '%s'", name)
            return True

    def get_active(self) -> Optional[Theme]:
        with self._lock:
            if not self._active_file.exists():
                return None
            name = self._active_file.read_text(encoding="utf-8").strip()
            if not name:
                return None
            return self.load(name)

    def set_active(self, name: str) -> None:
        with self._lock:
            if not self._path_for(name).exists():
                raise KeyError(f"Theme '{name}' does not exist in JSONThemeStore.")
            self._active_file.write_text(name, encoding="utf-8")
            logger.info("JSONThemeStore.set_active: '%s'", name)


# ---------------------------------------------------------------------------
# YAML adapter
# ---------------------------------------------------------------------------

class YAMLThemeStore(ThemeStore):
    """
    Stores themes as YAML files under a local directory.
    Requires PyYAML: pip install 'stylepro[yaml]'

    Layout::

        {directory}/
            themes/
                my_theme.yaml
            active.txt
    """

    def __init__(self, directory: str | Path = ".stylepro"):
        try:
            import yaml as _yaml  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "YAMLThemeStore requires PyYAML. "
                "Install it with: pip install 'stylepro[yaml]'"
            ) from exc

        import yaml
        self._yaml = yaml
        self._dir = Path(directory)
        self._themes_dir = self._dir / "themes"
        self._active_file = self._dir / _ACTIVE_FILENAME
        self._lock = threading.RLock()
        self._themes_dir.mkdir(parents=True, exist_ok=True)
        logger.info("YAMLThemeStore initialised at '%s'", self._dir)

    def _path_for(self, name: str) -> Path:
        return self._themes_dir / f"{name}.yaml"

    def save(self, theme: Theme) -> None:
        with self._lock:
            path = self._path_for(theme.name)
            path.write_text(
                self._yaml.dump(theme.to_dict(), default_flow_style=False),
                encoding="utf-8",
            )
            logger.debug("YAMLThemeStore.save: wrote '%s'", path)

    def load(self, name: str) -> Optional[Theme]:
        with self._lock:
            path = self._path_for(name)
            if not path.exists():
                return None
            data = self._yaml.safe_load(path.read_text(encoding="utf-8"))
            return Theme.from_dict(data)

    def list_themes(self) -> list[str]:
        with self._lock:
            return sorted(p.stem for p in self._themes_dir.glob("*.yaml"))

    def delete(self, name: str) -> bool:
        with self._lock:
            path = self._path_for(name)
            if not path.exists():
                return False
            path.unlink()
            if self._active_file.exists():
                if self._active_file.read_text(encoding="utf-8").strip() == name:
                    self._active_file.unlink()
            return True

    def get_active(self) -> Optional[Theme]:
        with self._lock:
            if not self._active_file.exists():
                return None
            name = self._active_file.read_text(encoding="utf-8").strip()
            return self.load(name) if name else None

    def set_active(self, name: str) -> None:
        with self._lock:
            if not self._path_for(name).exists():
                raise KeyError(f"Theme '{name}' does not exist in YAMLThemeStore.")
            self._active_file.write_text(name, encoding="utf-8")
            logger.info("YAMLThemeStore.set_active: '%s'", name)


# ---------------------------------------------------------------------------
# SQLite adapter
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS themes (
    name      TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0
);
"""


class SQLiteThemeStore(ThemeStore):
    """
    Stores themes in a SQLite database (stdlib only, no extra deps).

    Uses WAL journal mode for better concurrent read performance.
    Thread-safe via a per-instance reentrant lock + SQLite's own isolation.
    """

    def __init__(self, db_path: str | Path = ".stylepro/themes.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()
        logger.info("SQLiteThemeStore initialised at '%s'", self._db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------

    def save(self, theme: Theme) -> None:
        with self._lock:
            data = json.dumps(theme.to_dict())
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO themes (name, data) VALUES (?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET data = excluded.data;",
                    (theme.name, data),
                )
            logger.debug("SQLiteThemeStore.save: '%s'", theme.name)

    def load(self, name: str) -> Optional[Theme]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT data FROM themes WHERE name = ?;", (name,)
                ).fetchone()
            if row is None:
                return None
            return Theme.from_dict(json.loads(row["data"]))

    def list_themes(self) -> list[str]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT name FROM themes ORDER BY name;"
                ).fetchall()
            return [r["name"] for r in rows]

    def delete(self, name: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM themes WHERE name = ?;", (name,)
                )
            existed = cursor.rowcount > 0
            if existed:
                logger.info("SQLiteThemeStore.delete: removed '%s'", name)
            return existed

    def get_active(self) -> Optional[Theme]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT data FROM themes WHERE is_active = 1 LIMIT 1;"
                ).fetchone()
            if row is None:
                return None
            return Theme.from_dict(json.loads(row["data"]))

    def set_active(self, name: str) -> None:
        with self._lock:
            with self._connect() as conn:
                # Verify theme exists first.
                exists = conn.execute(
                    "SELECT 1 FROM themes WHERE name = ?;", (name,)
                ).fetchone()
                if not exists:
                    raise KeyError(f"Theme '{name}' does not exist in SQLiteThemeStore.")
                conn.execute("UPDATE themes SET is_active = 0;")
                conn.execute(
                    "UPDATE themes SET is_active = 1 WHERE name = ?;", (name,)
                )
            logger.info("SQLiteThemeStore.set_active: '%s'", name)
