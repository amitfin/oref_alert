"""Helper for loading area to polygon map."""

import json
import zipfile
from io import BytesIO
from pathlib import Path

import aiofiles
from shapely.geometry import Point, Polygon

_area_to_polygon: dict[str, list[tuple[float, float]]] = {}


async def init_area_to_polygon() -> None:
    """Unzip and load the area to polygon map."""
    global _area_to_polygon  # noqa: PLW0603
    if _area_to_polygon:
        return
    async with aiofiles.open(
        Path(__file__).with_suffix(".json.zip"), mode="rb"
    ) as zip_file_raw:
        zip_raw = await zip_file_raw.read()
    with (
        zipfile.ZipFile(BytesIO(zip_raw)) as zip_file,
        zip_file.open(f"{Path(__file__).stem}.json") as json_file,
    ):
        _area_to_polygon = json.load(json_file)


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
