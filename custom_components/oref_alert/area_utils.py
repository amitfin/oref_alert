"""Utilities for metadata information."""

from .metadata.city_all_areas import CITY_ALL_AREAS
from .metadata.district_to_areas import DISTRICT_AREAS


def expand_areas_and_groups(areas_and_groups: list[str]) -> list[str]:
    """Expand groups (if exists) to areas."""
    areas = []
    for area_or_group in areas_and_groups:
        if area_or_group in CITY_ALL_AREAS:
            areas.extend(CITY_ALL_AREAS[area_or_group])
        elif area_or_group in DISTRICT_AREAS:
            areas.extend(DISTRICT_AREAS[area_or_group])
        else:
            areas.append(area_or_group)
    areas.sort()
    return areas
