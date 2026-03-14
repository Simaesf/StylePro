"""
stylepro.utils.css
-------------------
CSS generation and sanitization utilities.
All functions are stateless and pure — no class state, no side effects.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stylepro.core.theme import Theme

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security: patterns that must never appear in CSS values
# ---------------------------------------------------------------------------
_BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"url\s*\(", re.IGNORECASE),
    re.compile(r"expression\s*\(", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"@import", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"behavior\s*:", re.IGNORECASE),
    re.compile(r"vbscript\s*:", re.IGNORECASE),
    re.compile(r"data\s*:", re.IGNORECASE),
    re.compile(r"-moz-binding", re.IGNORECASE),
]

# Allowlist for CSS custom-property values.
# Matches: hex colours, rgb/rgba/hsl/hsla functions, plain numbers with
# optional units, named CSS keywords, blank/empty values, and CSS
# calc()/var() expressions (without dangerous sub-patterns).
_SAFE_VALUE_RE = re.compile(
    r"""^
    (?:
        \#[0-9a-fA-F]{3,8}                              # hex colour
        | (?:rgb|rgba|hsl|hsla)\([^)]*\)                # colour functions
        | -?[0-9]+(?:\.[0-9]+)?(?:px|em|rem|%|vh|vw|vmin|vmax|pt|cm|mm|s|ms)?
                                                         # numbers with units
        | (?:normal|bold|italic|none|auto|inherit|initial|unset|revert
             |transparent|currentColor|solid|dashed|dotted|left|right
             |center|top|bottom|flex|block|inline|grid|hidden|visible
             |scroll|clip|ellipsis|nowrap|break-word|pointer|default
             |crosshair|move|grab|grabbing|zoom-in|zoom-out|text
             |not-allowed|col-resize|row-resize|se-resize|nw-resize
             |ne-resize|sw-resize|n-resize|s-resize|e-resize|w-resize)
                                                         # safe CSS keywords
        | calc\([^)]*\)                                  # calc()
        | var\(--[a-zA-Z0-9_-]+\)                        # var(--name)
        | [a-zA-Z][a-zA-Z0-9_-]*                         # unquoted keywords
        | "(?:[^"\\]|\\.)*"                              # double-quoted string
        | '(?:[^'\\]|\\.)*'                              # single-quoted string
        | \s+                                            # whitespace (between tokens)
    )*$
    """,
    re.VERBOSE,
)

# CSS variable name: must start with -- and contain only safe chars.
_SAFE_VAR_NAME_RE = re.compile(r"^--[a-zA-Z][a-zA-Z0-9_-]*$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_css_value(value: str) -> str:
    """
    Strip or reject dangerous CSS constructs from *value*.

    Raises ValueError if the value matches a known dangerous pattern.
    Returns the stripped/trimmed value on success.
    """
    stripped = value.strip()

    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(stripped):
            raise ValueError(
                f"CSS value rejected — contains disallowed construct "
                f"(matched {pattern.pattern!r}): {stripped!r}"
            )

    if not _SAFE_VALUE_RE.match(stripped) and stripped != "":
        logger.warning(
            "CSS value '%s' did not match the safe-value allowlist; "
            "it will be used but review it manually.",
            stripped,
        )

    return stripped


def sanitize_variable_name(name: str, prefix: str = "--sp") -> str:
    """
    Ensure *name* is a valid CSS custom-property name that starts with *prefix*.

    - Strips characters outside [a-zA-Z0-9_-].
    - Prepends *prefix* if not already present.
    - Raises ValueError if the result is not a valid custom-property name.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", name.lstrip("-"))
    if not cleaned:
        raise ValueError(f"Cannot derive a valid CSS variable name from: {name!r}")

    full_name = f"{prefix}-{cleaned}" if not name.startswith(prefix) else name

    if not _SAFE_VAR_NAME_RE.match(full_name):
        raise ValueError(
            f"Variable name {full_name!r} is not a valid CSS custom property name."
        )

    return full_name


def variables_to_css_block(selector: str, variables: dict[str, str]) -> str:
    """
    Render one CSS block::

        selector {
          --var-name: value;
        }

    *variables* maps CSS variable name -> value string.
    Empty *variables* returns an empty string.
    """
    if not variables:
        return ""

    lines = []
    for name, value in sorted(variables.items()):
        # CSS custom properties (--sp-*) do not use !important — it causes
        # unexpected cascade behaviour in browsers.
        # Regular CSS properties (e.g. background-color) need !important to
        # override framework styles such as Streamlit's button rules.
        suffix = "" if name.startswith("--") else " !important"
        lines.append(f"  {name}: {value}{suffix};")
    return f"{selector} {{\n" + "\n".join(lines) + "\n}"


def theme_to_css(theme: "Theme") -> str:
    """
    Render a Theme object as a complete CSS string.

    Global variables (element_selector=None) are grouped under :root {}.
    Element-scoped variables are grouped under their selector block.
    Selectors are emitted in sorted order for deterministic output.
    """
    global_vars: dict[str, str] = {}
    scoped_vars: dict[str, dict[str, str]] = defaultdict(dict)

    for var in theme.variables.values():
        if var.element_selector is None:
            global_vars[var.name] = var.value
        else:
            scoped_vars[var.element_selector][var.name] = var.value

    blocks: list[str] = []

    if global_vars:
        blocks.append(variables_to_css_block(":root", global_vars))

    for selector in sorted(scoped_vars):
        blocks.append(variables_to_css_block(selector, scoped_vars[selector]))

    css = "\n\n".join(filter(None, blocks))
    logger.debug("theme_to_css: generated %d chars for theme '%s'", len(css), theme.name)
    return css


def merge_css_blocks(blocks: list[str]) -> str:
    """
    Merge a list of CSS block strings.

    Rules within the same selector are deduplicated — later blocks win
    on property conflicts.  Selector order from the first occurrence is
    preserved; properties use the last-seen value.
    """
    # Parse each block into {selector: {property: value}}
    selector_order: list[str] = []
    merged: dict[str, dict[str, str]] = {}

    _rule_re = re.compile(
        r"([^{]+)\s*\{([^}]*)\}",
        re.DOTALL,
    )
    _prop_re = re.compile(r"(--[a-zA-Z][a-zA-Z0-9_-]*)\s*:\s*([^;]+);")

    for block in blocks:
        for rule_match in _rule_re.finditer(block):
            selector = rule_match.group(1).strip()
            declarations = rule_match.group(2)

            if selector not in merged:
                selector_order.append(selector)
                merged[selector] = {}

            for prop_match in _prop_re.finditer(declarations):
                merged[selector][prop_match.group(1).strip()] = prop_match.group(2).strip()

    result_blocks: list[str] = []
    for selector in selector_order:
        result_blocks.append(variables_to_css_block(selector, merged[selector]))

    return "\n\n".join(filter(None, result_blocks))
