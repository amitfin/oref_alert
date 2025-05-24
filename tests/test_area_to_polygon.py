"""The tests for the area_to_polygon file."""

import pytest

from custom_components.oref_alert.metadata.area_to_polygon import async_find_area


@pytest.mark.parametrize(
    ("lat", "lon", "area"),
    [
        (32.07213574931027, 34.87900299521438, "פתח תקווה"),
        (32.055015343092336, 34.75616061215727, "תל אביב - דרום העיר ויפו"),
        (32.064548784776356, 34.756806911890585, None),
    ],
    ids=("regular", "big city multiple areas", "in the sea"),
)
async def test_find_area(lat: float, lon: float, area: str | None) -> None:
    """Test finding an area using coordinate."""
    assert await async_find_area(lat, lon) == area
