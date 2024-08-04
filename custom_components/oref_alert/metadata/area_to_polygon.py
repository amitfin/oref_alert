"""Helper for loading area to polygon map."""

import json
import zipfile
from pathlib import Path

from shapely.geometry import Point, Polygon


def _load_area_to_polygon() -> dict[str, list[list[float]]]:
    """Return the map of area to list of tuples with (lat, long) coordinates."""
    with (
        zipfile.ZipFile(Path(__file__).with_suffix(".json.zip")) as zip_file,
        zip_file.open(f"{Path(__file__).stem}.json") as json_file,
    ):
        return json.load(json_file)


def find_area(lat: float, long: float) -> str | None:
    """Find an area using lat/long."""
    point = Point(lat, long)
    for area, polygon in _load_area_to_polygon().items():
        if Polygon(polygon).contains(point):
            return area
    return None
