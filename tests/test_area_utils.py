"""The tests for the area_utils file."""

import pytest

from custom_components.oref_alert.area_utils import expand_areas_and_groups
from custom_components.oref_alert.metadata import ALL_AREAS_ALIASES
from custom_components.oref_alert.metadata.areas import AREAS


@pytest.mark.parametrize(
    ("input_list", "output_list"),
    [
        (["פתח תקווה"], ["פתח תקווה"]),
        (["מחוז אילת"], ["אזור תעשייה שחורת", "אילות", "אילת"]),
        (
            ["מחוז אילת", "אביבים"],
            [
                "אביבים",
                "אזור תעשייה שחורת",
                "אילות",
                "אילת",
            ],
        ),
    ],
    ids=("single no expansion", "district", "mix"),
)
async def test_single_area(input_list: list[str], output_list: list[str]) -> None:
    """Test a single area, no expansion."""
    assert expand_areas_and_groups(input_list) == output_list


def test_all_areas_aliases() -> None:
    """Test all areas aliases."""
    assert ALL_AREAS_ALIASES.issubset(AREAS)
