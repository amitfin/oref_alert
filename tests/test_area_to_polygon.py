"""The tests for the area_to_polygon file."""

from __future__ import annotations

import gzip
from typing import TYPE_CHECKING

import pytest
from shapely.geometry import Polygon

from custom_components.oref_alert.metadata import area_to_polygon
from custom_components.oref_alert.metadata.area_to_polygon import (
    async_find_area,
    init_area_to_polygon,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("write_plain", "write_gz"),
    [(True, False), (False, True), (True, True)],
    ids=("plain", "gzip", "both"),
)
async def test_init_area_to_polygon_reads_plain_or_gzip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    write_plain: bool,
    write_gz: bool,
) -> None:
    """Test loading from the plain file (git) or the .gz file (release)."""
    plain = tmp_path / "polygons.json"
    gz = tmp_path / "polygons.json.gz"
    content = b'{\n"Area A":[[1.5,2.5],[3,4]]\n}\n'
    if write_plain:
        plain.write_bytes(content)
    if write_gz:
        # When both exist, the stale .gz must lose to the plain file.
        stale = b'{"Area A":[[0,0]]}' if write_plain else content
        gz.write_bytes(gzip.compress(stale))
    monkeypatch.setattr(area_to_polygon, "POLYGONS_FILE", plain)
    monkeypatch.setattr(area_to_polygon, "POLYGONS_GZ_FILE", gz)
    monkeypatch.setattr(area_to_polygon, "_area_to_polygon", {})

    assert await init_area_to_polygon() == {"Area A": [[1.5, 2.5], [3, 4]]}


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


@pytest.mark.slow
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
