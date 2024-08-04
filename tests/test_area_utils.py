"""The tests for the area_utils file."""

import pytest

from custom_components.oref_alert.area_utils import expand_areas_and_groups


@pytest.mark.parametrize(
    ("input_list", "output_list"),
    [
        (["פתח תקווה"], ["פתח תקווה"]),
        (
            ["תל אביב - כל האזורים"],
            [
                "תל אביב - דרום העיר ויפו",
                "תל אביב - מזרח",
                "תל אביב - מרכז העיר",
                "תל אביב - עבר הירקון",
            ],
        ),
        (["מחוז אילת"], ["אזור תעשייה שחורת", "אילות", "אילת"]),
        (
            ["מחוז אילת", "אביבים", "נתניה - כל האזורים"],
            [
                "אביבים",
                "אזור תעשייה שחורת",
                "אילות",
                "אילת",
                "נתניה - מזרח",
                "נתניה - מערב",
            ],
        ),
    ],
    ids=("single no expansion", "all areas", "district", "mix"),
)
async def test_single_area(input_list: list[str], output_list: list[str]) -> None:
    """Test a single area, no expansion."""
    assert expand_areas_and_groups(input_list) == output_list
