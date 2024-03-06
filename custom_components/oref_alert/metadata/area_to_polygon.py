"""Helper for loading area to polygon map."""

import json
from os import path
import zipfile

from shapely.geometry import Point, Polygon


def _load_area_to_polygon() -> dict[str, list[list[float]]]:
    """Return the map of area to list of tupples with (lat, long) coordinates."""
    with (
        zipfile.ZipFile(f"{path.splitext(__file__)[0]}.json.zip") as zip_file,
        zip_file.open(f"{path.splitext(path.basename(__file__))[0]}.json") as json_file,
    ):
        return json.load(json_file)


def find_area(lat: float, long: float) -> str | None:
    """Find an area using lat/long."""
    point = Point(lat, long)
    for area, polygon in _load_area_to_polygon().items():
        if Polygon(polygon).contains(point):
            return area
    return None
