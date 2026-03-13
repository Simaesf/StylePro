"""
Tests for stylepro.utils.css.
"""

import pytest
from stylepro.utils.css import (
    sanitize_css_value,
    sanitize_variable_name,
    variables_to_css_block,
    theme_to_css,
    merge_css_blocks,
)
from stylepro.core.theme import Theme, ThemeVariable


# ---------------------------------------------------------------------------
# sanitize_css_value
# ---------------------------------------------------------------------------

def test_sanitize_allows_hex_color():
    assert sanitize_css_value("#ff5733") == "#ff5733"
    assert sanitize_css_value("  #abc  ") == "#abc"


def test_sanitize_allows_rgb():
    assert sanitize_css_value("rgb(255, 87, 51)") == "rgb(255, 87, 51)"


def test_sanitize_allows_px_value():
    assert sanitize_css_value("16px") == "16px"
    assert sanitize_css_value("1.5rem") == "1.5rem"


def test_sanitize_allows_keywords():
    assert sanitize_css_value("none") == "none"
    assert sanitize_css_value("bold") == "bold"


def test_sanitize_blocks_url():
    with pytest.raises(ValueError, match="disallowed construct"):
        sanitize_css_value("url(http://evil.com)")


def test_sanitize_blocks_javascript():
    with pytest.raises(ValueError, match="disallowed construct"):
        sanitize_css_value("javascript:alert(1)")


def test_sanitize_blocks_expression():
    with pytest.raises(ValueError, match="disallowed construct"):
        sanitize_css_value("expression(alert(1))")


def test_sanitize_blocks_import():
    with pytest.raises(ValueError, match="disallowed construct"):
        sanitize_css_value("@import url('x.css')")


# ---------------------------------------------------------------------------
# sanitize_variable_name
# ---------------------------------------------------------------------------

def test_sanitize_var_name_adds_prefix():
    result = sanitize_variable_name("bg-color")
    assert result == "--sp-bg-color"


def test_sanitize_var_name_keeps_existing_prefix():
    result = sanitize_variable_name("--sp-text-color")
    assert result == "--sp-text-color"


def test_sanitize_var_name_strips_bad_chars():
    result = sanitize_variable_name("bg color!")
    assert result.startswith("--sp-")


def test_sanitize_var_name_raises_on_empty():
    with pytest.raises(ValueError):
        sanitize_variable_name("!!!###")


# ---------------------------------------------------------------------------
# variables_to_css_block
# ---------------------------------------------------------------------------

def test_variables_to_css_block_basic():
    css = variables_to_css_block(":root", {"--sp-bg": "#fff", "--sp-fg": "#000"})
    assert ":root {" in css
    assert "--sp-bg: #fff;" in css
    assert "--sp-fg: #000;" in css


def test_variables_to_css_block_empty():
    assert variables_to_css_block(":root", {}) == ""


def test_variables_to_css_block_scoped_selector():
    css = variables_to_css_block("[data-sp-id='btn-1']", {"--sp-bg": "red"})
    assert "[data-sp-id='btn-1']" in css
    assert "--sp-bg: red;" in css


# ---------------------------------------------------------------------------
# theme_to_css
# ---------------------------------------------------------------------------

def _make_theme() -> Theme:
    return Theme(
        name="test",
        variables={
            "--sp-bg-color": ThemeVariable("--sp-bg-color", "#fff", "BG", "color"),
            "--sp-text-color": ThemeVariable("--sp-text-color", "#333", "Text", "color"),
            "--sp-btn": ThemeVariable(
                "--sp-btn", "#f00", "Button BG", "color",
                element_selector="[data-sp-id='btn-1']"
            ),
        },
    )


def test_theme_to_css_contains_root_block():
    css = theme_to_css(_make_theme())
    assert ":root {" in css
    assert "--sp-bg-color: #fff;" in css
    assert "--sp-text-color: #333;" in css


def test_theme_to_css_contains_scoped_block():
    css = theme_to_css(_make_theme())
    assert "[data-sp-id='btn-1']" in css
    assert "--sp-btn: #f00;" in css


def test_theme_to_css_empty_theme():
    css = theme_to_css(Theme(name="empty"))
    assert css == ""


# ---------------------------------------------------------------------------
# merge_css_blocks
# ---------------------------------------------------------------------------

def test_merge_css_blocks_later_wins():
    block_a = ":root {\n  --sp-bg: #fff;\n  --sp-fg: #000;\n}"
    block_b = ":root {\n  --sp-bg: #000;\n}"
    result = merge_css_blocks([block_a, block_b])
    # Later value for --sp-bg should win
    assert "--sp-bg: #000;" in result
    # --sp-fg from block_a should still be present
    assert "--sp-fg: #000;" in result


def test_merge_css_blocks_preserves_selector_order():
    block_a = ":root {\n  --sp-a: 1px;\n}"
    block_b = "[data-sp-id='x'] {\n  --sp-b: 2px;\n}"
    result = merge_css_blocks([block_a, block_b])
    assert ":root" in result
    assert "[data-sp-id='x']" in result


def test_merge_css_blocks_empty_list():
    assert merge_css_blocks([]) == ""
