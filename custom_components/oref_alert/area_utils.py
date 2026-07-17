"""Utilities for metadata information."""

from __future__ import annotations

from typing import Final

from .metadata import ALL_AREAS_ALIASES
from .metadata.areas_and_groups import AREAS_AND_GROUPS
from .metadata.district_to_areas import DISTRICT_AREAS

AREAS_AND_GROUPS_WITHOUT_ALL_AREAS: Final = [
    area for area in AREAS_AND_GROUPS if area not in ALL_AREAS_ALIASES
]


def expand_areas_and_groups(areas_and_groups: list[str]) -> list[str]:
    """Expand groups (if exists) to areas."""
    areas = []
    for area_or_group in areas_and_groups:
        if area_or_group in DISTRICT_AREAS:
            areas.extend(DISTRICT_AREAS[area_or_group])
        else:
            areas.append(area_or_group)
    areas.sort()
    return areas
