"""
Tests for stylepro.core.store — JSON, YAML, and SQLite adapters.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from stylepro.core.theme import Theme, ThemeVariable
from stylepro.core.store import JSONThemeStore, SQLiteThemeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _theme(name: str, bg: str = "#ffffff") -> Theme:
    return Theme(
        name=name,
        variables={
            "--sp-bg": ThemeVariable("--sp-bg", bg, "BG", "color"),
        },
        metadata={"framework": "test"},
    )


# ---------------------------------------------------------------------------
# JSONThemeStore
# ---------------------------------------------------------------------------

class TestJSONThemeStore:
    def test_save_and_load(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        t = _theme("default")
        store.save(t)
        loaded = store.load("default")
        assert loaded is not None
        assert loaded.name == "default"
        assert loaded.variables["--sp-bg"].value == "#ffffff"

    def test_load_missing_returns_none(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        assert store.load("nonexistent") is None

    def test_list_themes(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        store.save(_theme("alpha"))
        store.save(_theme("beta"))
        store.save(_theme("gamma"))
        assert store.list_themes() == ["alpha", "beta", "gamma"]

    def test_delete_existing(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        store.save(_theme("to_delete"))
        assert store.delete("to_delete") is True
        assert store.load("to_delete") is None

    def test_delete_nonexistent(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        assert store.delete("ghost") is False

    def test_active_theme_round_trip(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        assert store.get_active() is None
        store.save(_theme("dark"))
        store.set_active("dark")
        active = store.get_active()
        assert active is not None
        assert active.name == "dark"

    def test_set_active_raises_for_unknown(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        with pytest.raises(KeyError):
            store.set_active("nonexistent")

    def test_delete_clears_active(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        store.save(_theme("light"))
        store.set_active("light")
        store.delete("light")
        assert store.get_active() is None

    def test_save_overwrites(self, tmp_path):
        store = JSONThemeStore(tmp_path)
        store.save(_theme("t", bg="#fff"))
        store.save(_theme("t", bg="#000"))
        loaded = store.load("t")
        assert loaded.variables["--sp-bg"].value == "#000"

    def test_thread_safety(self, tmp_path):
        """Concurrent save/load must not corrupt data."""
        store = JSONThemeStore(tmp_path)
        errors: list[Exception] = []

        def worker(i: int):
            try:
                t = _theme(f"theme_{i}", bg=f"#{i:06x}")
                store.save(t)
                loaded = store.load(f"theme_{i}")
                assert loaded is not None
                assert loaded.name == f"theme_{i}"
            except Exception as exc:
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(worker, range(20)))

        assert errors == [], f"Thread-safety errors: {errors}"
        assert len(store.list_themes()) == 20


# ---------------------------------------------------------------------------
# SQLiteThemeStore
# ---------------------------------------------------------------------------

class TestSQLiteThemeStore:
    def test_save_and_load(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        t = _theme("default")
        store.save(t)
        loaded = store.load("default")
        assert loaded is not None
        assert loaded.variables["--sp-bg"].value == "#ffffff"

    def test_load_missing_returns_none(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        assert store.load("ghost") is None

    def test_list_themes(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        store.save(_theme("alpha"))
        store.save(_theme("beta"))
        assert store.list_themes() == ["alpha", "beta"]

    def test_delete_existing(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        store.save(_theme("bye"))
        assert store.delete("bye") is True
        assert store.load("bye") is None

    def test_delete_nonexistent(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        assert store.delete("ghost") is False

    def test_active_theme(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        assert store.get_active() is None
        store.save(_theme("dark"))
        store.set_active("dark")
        active = store.get_active()
        assert active is not None
        assert active.name == "dark"

    def test_set_active_clears_previous(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        store.save(_theme("light"))
        store.save(_theme("dark"))
        store.set_active("light")
        store.set_active("dark")
        assert store.get_active().name == "dark"

    def test_set_active_raises_for_unknown(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        with pytest.raises(KeyError):
            store.set_active("ghost")

    def test_save_overwrites(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        store.save(_theme("t", bg="#fff"))
        store.save(_theme("t", bg="#000"))
        assert store.load("t").variables["--sp-bg"].value == "#000"

    def test_thread_safety(self, tmp_path):
        store = SQLiteThemeStore(tmp_path / "themes.db")
        errors: list[Exception] = []

        def worker(i: int):
            try:
                t = _theme(f"theme_{i}", bg=f"#{i:06x}")
                store.save(t)
                loaded = store.load(f"theme_{i}")
                assert loaded is not None
            except Exception as exc:
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(worker, range(20)))

        assert errors == [], f"Thread-safety errors: {errors}"


# ---------------------------------------------------------------------------
# YAMLThemeStore — only tested if PyYAML is available
# ---------------------------------------------------------------------------

try:
    import yaml  # noqa: F401
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


@pytest.mark.skipif(not _YAML_AVAILABLE, reason="PyYAML not installed")
class TestYAMLThemeStore:
    def test_save_and_load(self, tmp_path):
        from stylepro.core.store import YAMLThemeStore
        store = YAMLThemeStore(tmp_path)
        t = _theme("default")
        store.save(t)
        loaded = store.load("default")
        assert loaded is not None
        assert loaded.variables["--sp-bg"].value == "#ffffff"

    def test_list_themes(self, tmp_path):
        from stylepro.core.store import YAMLThemeStore
        store = YAMLThemeStore(tmp_path)
        store.save(_theme("a"))
        store.save(_theme("b"))
        assert store.list_themes() == ["a", "b"]


def test_yaml_store_raises_without_pyyaml(monkeypatch):
    """YAMLThemeStore gives a clear error when PyYAML is missing."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from stylepro.core.store import YAMLThemeStore
    with pytest.raises(ImportError, match="PyYAML"):
        YAMLThemeStore("/tmp/test")
