"""The tests for the category_symbol file."""

import pytest

from custom_components.oref_alert.categories import (
    CATEGORY_METADATA,
    category_is_alert,
    category_is_update,
    category_to_emoji,
    category_to_icon,
    real_time_to_history_category,
)


def test_all() -> None:
    """Test all values."""
    for category, symbols in CATEGORY_METADATA.items():
        assert category_to_icon(category) == f"mdi:{symbols[0]}"
        assert category_to_emoji(category) == symbols[1]


@pytest.mark.parametrize("category", [(0,), (-1,), (29,)])
def test_out_of_range(category: int) -> None:
    """Test non existence categories."""
    assert category_to_icon(category) == "mdi:alert"
    assert category_to_emoji(category) == "🚨"


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (-1, False),
        (0, False),
        (1, True),
        (5, False),
        (13, False),
        (14, False),
        (15, False),
        (100, False),
    ],
)
def test_category_is_alert(category: int, expected: bool) -> None:  # noqa: FBT001
    """Test category_is_alert."""
    assert category_is_alert(category) == expected


def test_category_is_update() -> None:
    """Test category_is_update."""
    assert category_is_update(13) is True
    assert category_is_update(14) is True
    assert category_is_update(12) is False
    assert category_is_update(real_time_to_history_category(10) or 0) is True
    assert category_is_update(real_time_to_history_category(13) or 0) is False


def test_real_time_to_history_category() -> None:
    """Test real_time_to_history_category."""
    for category, expected in enumerate(
        [None, 1, 4, 7, 9, 11, 2, 12, None, None, 13, None, None, 10, None]
    ):
        assert real_time_to_history_category(category) == expected
