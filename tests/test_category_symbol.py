"""The tests for the category_symbol file."""

import pytest

from custom_components.oref_alert.category_symbol import (
    CATEGORY_TO_ICON_EMOJI,
    category_to_emoji,
    category_to_icon,
)


def test_all() -> None:
    """Test all values."""
    for category, symbols in CATEGORY_TO_ICON_EMOJI.items():
        assert category_to_icon(category) == f"mdi:{symbols[0]}"
        assert category_to_emoji(category) == symbols[1]


@pytest.mark.parametrize("category", [(0,), (-1,), (29,)])
def test_out_of_range(category: int) -> None:
    """Test non existence categories."""
    assert category_to_icon(category) == "mdi:alert"
    assert category_to_emoji(category) == "🚨"
