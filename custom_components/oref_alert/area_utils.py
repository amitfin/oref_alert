"""Utilities for metadata information."""

from __future__ import annotations

from .metadata.district_to_areas import DISTRICT_AREAS


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
