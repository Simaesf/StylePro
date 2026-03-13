"""
stylepro.core.theme
-------------------
Theme data model.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ThemeVariable:
    """A single CSS custom-property entry within a theme."""

    name: str
    """CSS variable name, e.g. '--sp-bg-color'."""

    value: str
    """CSS value string, e.g. '#ffffff' or '16px'."""

    label: str
    """Human-readable label shown in the editor UI."""

    category: str
    """One of: 'color', 'spacing', 'typography', 'border'."""

    element_selector: Optional[str] = None
    """
    When set, this variable is scoped to a specific element selector such as
    \"[data-sp-id='btn-a3f2']\".  When None the variable is global (:root).
    """

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "label": self.label,
            "category": self.category,
            "element_selector": self.element_selector,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThemeVariable":
        return cls(
            name=data["name"],
            value=data["value"],
            label=data.get("label", data["name"]),
            category=data.get("category", "color"),
            element_selector=data.get("element_selector"),
        )


@dataclass
class Theme:
    """A named collection of ThemeVariable entries."""

    name: str
    variables: dict[str, ThemeVariable] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    """
    Arbitrary key/value metadata.
    Common keys: created_by, created_at, framework, description.
    """

    # ------------------------------------------------------------------
    # CSS rendering
    # ------------------------------------------------------------------

    def to_css(self) -> str:
        """
        Render the theme as a complete CSS string using CSS custom properties.

        Global variables (element_selector=None) go under :root {}.
        Element-scoped variables are grouped under their selector.
        """
        from stylepro.utils.css import theme_to_css
        return theme_to_css(self)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "name": self.name,
            "variables": {k: v.to_dict() for k, v in self.variables.items()},
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        """Deserialise from a stored dict (as produced by to_dict())."""
        variables = {
            k: ThemeVariable.from_dict(v)
            for k, v in data.get("variables", {}).items()
        }
        theme = cls(
            name=data["name"],
            variables=variables,
            metadata=data.get("metadata", {}),
        )
        logger.debug("Theme.from_dict: loaded theme '%s' (%d vars)", theme.name, len(variables))
        return theme

    # ------------------------------------------------------------------
    # Immutable operations — return new Theme instances
    # ------------------------------------------------------------------

    def merge(self, other: "Theme") -> "Theme":
        """
        Return a new Theme whose variables are the union of self and *other*,
        with *other*'s values taking precedence on conflict.
        The returned theme keeps self's name and metadata unless *other* supplies
        non-empty metadata.
        """
        merged_vars = {**copy.deepcopy(self.variables), **copy.deepcopy(other.variables)}
        merged_meta = {**self.metadata, **other.metadata}
        result = Theme(name=self.name, variables=merged_vars, metadata=merged_meta)
        logger.debug(
            "Theme.merge: '%s' + '%s' -> %d vars", self.name, other.name, len(merged_vars)
        )
        return result

    def apply_patch(self, patch: dict[str, str]) -> "Theme":
        """
        Return a new Theme with selected variable values updated.

        *patch* maps variable name -> new value string, e.g.::

            {'--sp-bg-color': '#000000', '--sp-text-color': '#ffffff'}

        Variables referenced in *patch* that do not exist in self are created
        with a minimal ThemeVariable (label=name, category='color').
        """
        new_vars = copy.deepcopy(self.variables)
        for var_name, new_value in patch.items():
            if var_name in new_vars:
                new_vars[var_name] = ThemeVariable(
                    name=new_vars[var_name].name,
                    value=new_value,
                    label=new_vars[var_name].label,
                    category=new_vars[var_name].category,
                    element_selector=new_vars[var_name].element_selector,
                )
            else:
                logger.debug(
                    "Theme.apply_patch: creating new variable '%s' in theme '%s'",
                    var_name, self.name,
                )
                new_vars[var_name] = ThemeVariable(
                    name=var_name,
                    value=new_value,
                    label=var_name,
                    category="color",
                )

        return Theme(name=self.name, variables=new_vars, metadata=dict(self.metadata))
