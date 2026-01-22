"""The tests for the area_to_polygon file."""

import os
import itertools

import pytest
from shapely.geometry import Polygon

from custom_components.oref_alert.metadata.area_to_polygon import (
    async_find_area,
    init_area_to_polygon,
)


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


@pytest.mark.skipif(
    not os.getenv("GITHUB_ACTIONS"),
    reason="slow test; run only in GitHub Actions",
)
async def test_polygons_do_not_overlap() -> None:
    """Ensure no polygons overlap each other."""
    areas = list((await init_area_to_polygon()).items())
    polygons = [Polygon(coords) for _, coords in areas]
    overlaps: list[str] = []

    for index_a, (name_a, _) in enumerate(areas):
        poly_a = polygons[index_a]
        for index_b in range(index_a + 1, len(areas)):
            name_b = areas[index_b][0]
            poly_b = polygons[index_b]
            if poly_a.intersection(poly_b).area > 0:
                overlaps.append(f"{name_a} <-> {name_b}")

    assert not overlaps, f"Overlapping areas: {', '.join(overlaps)}"
