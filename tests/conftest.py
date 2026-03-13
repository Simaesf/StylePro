"""
Shared pytest fixtures for the StylePro test suite.
"""

import pytest


@pytest.fixture
def sample_theme_dict():
    """A minimal theme dict used across multiple tests."""
    return {
        "name": "test_theme",
        "variables": {
            "--sp-bg-color": {
                "name": "--sp-bg-color",
                "value": "#ffffff",
                "label": "Background Color",
                "category": "color",
                "element_selector": None,
            },
            "--sp-text-color": {
                "name": "--sp-text-color",
                "value": "#333333",
                "label": "Text Color",
                "category": "color",
                "element_selector": None,
            },
        },
        "metadata": {
            "created_by": "test",
            "framework": "test",
        },
    }
