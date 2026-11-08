"""Helper for loading area to polygon map."""

import gzip
import json
from pathlib import Path
from typing import Final

import aiofiles
from shapely.geometry import Point, Polygon

# Git holds the plain file. The release ships only the gzip-compressed version.
POLYGONS_FILE: Final = Path(__file__).with_suffix(".json")
POLYGONS_GZ_FILE: Final = Path(__file__).with_suffix(".json.gz")

_area_to_polygon: dict[str, list[tuple[float, float]]] = {}


async def init_area_to_polygon() -> dict[str, list[tuple[float, float]]]:
    """Load the area to polygon map (plain in git, compressed in a release)."""
    global _area_to_polygon  # noqa: PLW0603
    if _area_to_polygon:
        return _area_to_polygon
    # The plain file wins, since the metadata generator only updates it.
    try:
        async with aiofiles.open(POLYGONS_FILE, mode="rb") as file:
            content = await file.read()
    except FileNotFoundError:
        async with aiofiles.open(POLYGONS_GZ_FILE, mode="rb") as file:
            content = gzip.decompress(await file.read())
    _area_to_polygon = json.loads(content)
    return _area_to_polygon


def find_area(lat: float, lon: float) -> str | None:
    """Find an area using lat/lon."""
    point = Point(lat, lon)
    for area, polygon in _area_to_polygon.items():
        if Polygon(polygon).contains(point):
            return area
    return None


async def async_find_area(lat: float, lon: float) -> str | None:
    """Find an area using lat/lon."""
    await init_area_to_polygon()
    return find_area(lat, lon)


def area_to_polygon(area: str | None) -> list[tuple[float, float]] | None:
    """Return area's polygon."""
    return _area_to_polygon.get(area) if area else None
