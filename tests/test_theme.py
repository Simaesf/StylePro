"""
Tests for stylepro.core.theme.
"""

import pytest
from stylepro.core.theme import Theme, ThemeVariable


def test_imports():
    assert Theme
    assert ThemeVariable


def test_theme_variable_fields():
    tv = ThemeVariable(
        name="--sp-bg-color",
        value="#fff",
        label="Background",
        category="color",
    )
    assert tv.name == "--sp-bg-color"
    assert tv.element_selector is None


def test_theme_variable_to_dict():
    tv = ThemeVariable("--sp-bg", "#fff", "BG", "color", "[data-sp-id='x']")
    d = tv.to_dict()
    assert d["name"] == "--sp-bg"
    assert d["element_selector"] == "[data-sp-id='x']"


def test_theme_variable_from_dict_round_trip():
    tv = ThemeVariable("--sp-bg", "#fff", "BG", "color")
    assert ThemeVariable.from_dict(tv.to_dict()) == tv


def test_theme_fields():
    t = Theme(name="my_theme")
    assert t.name == "my_theme"
    assert t.variables == {}
    assert t.metadata == {}


def test_theme_to_css():
    t = Theme(
        name="t",
        variables={
            "--sp-bg": ThemeVariable("--sp-bg", "#fff", "BG", "color"),
        },
    )
    css = t.to_css()
    assert ":root {" in css
    assert "--sp-bg: #fff;" in css


def test_theme_round_trip():
    original = Theme(
        name="test",
        variables={
            "--sp-bg": ThemeVariable("--sp-bg", "#fff", "BG", "color"),
            "--sp-btn": ThemeVariable("--sp-btn", "#f00", "Btn", "color",
                                     "[data-sp-id='btn-1']"),
        },
        metadata={"framework": "streamlit"},
    )
    restored = Theme.from_dict(original.to_dict())
    assert restored.name == original.name
    assert restored.metadata == original.metadata
    assert len(restored.variables) == 2
    assert restored.variables["--sp-btn"].element_selector == "[data-sp-id='btn-1']"


def test_theme_merge():
    base = Theme(
        name="base",
        variables={"--sp-bg": ThemeVariable("--sp-bg", "#fff", "BG", "color")},
    )
    override = Theme(
        name="override",
        variables={"--sp-bg": ThemeVariable("--sp-bg", "#000", "BG", "color"),
                   "--sp-fg": ThemeVariable("--sp-fg", "#333", "FG", "color")},
    )
    merged = base.merge(override)
    assert merged.name == "base"
    assert merged.variables["--sp-bg"].value == "#000"
    assert "--sp-fg" in merged.variables


def test_theme_merge_does_not_mutate_originals():
    base = Theme(
        name="base",
        variables={"--sp-bg": ThemeVariable("--sp-bg", "#fff", "BG", "color")},
    )
    other = Theme(
        name="other",
        variables={"--sp-bg": ThemeVariable("--sp-bg", "#000", "BG", "color")},
    )
    base.merge(other)
    assert base.variables["--sp-bg"].value == "#fff"


def test_theme_apply_patch_updates_existing():
    t = Theme(
        name="t",
        variables={"--sp-bg": ThemeVariable("--sp-bg", "#fff", "BG", "color")},
    )
    patched = t.apply_patch({"--sp-bg": "#000"})
    assert patched.variables["--sp-bg"].value == "#000"
    # Original unchanged
    assert t.variables["--sp-bg"].value == "#fff"


def test_theme_apply_patch_creates_new_var():
    t = Theme(name="t", variables={})
    patched = t.apply_patch({"--sp-new-var": "42px"})
    assert "--sp-new-var" in patched.variables
    assert patched.variables["--sp-new-var"].value == "42px"
