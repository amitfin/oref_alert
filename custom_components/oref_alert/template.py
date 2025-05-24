"""Inject template extensions to the Home Assistant instance."""

# The injection logic is based on:
# https://github.com/PiotrMachowski/Home-Assistant-custom-components-Custom-Templates/blob/master/custom_components/custom_templates/__init__.py

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import (
    Template,
    TemplateEnvironment,
)
from homeassistant.helpers.template import (
    distance as distance_func,
)

from custom_components.oref_alert.categories import category_to_emoji, category_to_icon
from custom_components.oref_alert.metadata.area_info import AREA_INFO
from custom_components.oref_alert.metadata.area_to_migun_time import AREA_TO_MIGUN_TIME
from custom_components.oref_alert.metadata.area_to_polygon import (
    find_area,
    init_area_to_polygon,
)
from custom_components.oref_alert.metadata.areas import AREAS
from custom_components.oref_alert.metadata.areas_and_groups import AREAS_AND_GROUPS

from .const import (
    AREAS_TEMPLATE_FUNCTION,
    COORDINATE_TEMPLATE_FUNCTION,
    DISTANCE_TEMPLATE_FUNCTION,
    DISTANCE_TEST_TEMPLATE_FUNCTION,
    DISTRICT_TEMPLATE_FUNCTION,
    EMOJI_TEMPLATE_FUNCTION,
    FIND_AREA_TEMPLATE_FUNCTION,
    ICON_TEMPLATE_FUNCTION,
    SHELTER_TEMPLATE_FUNCTION,
)
from .metadata.area_to_district import AREA_TO_DISTRICT


async def inject_template_extensions(hass: HomeAssistant) -> None:
    """Inject template extension to the Home Assistant instance."""
    await init_area_to_polygon()

    def get_areas(groups: bool = False) -> list[str]:  # noqa: FBT001, FBT002
        """Get all areas."""
        return list(AREAS) if not groups else AREAS_AND_GROUPS

    def area_to_district(area: str) -> str:
        """Convert area to district."""
        return AREA_TO_DISTRICT.get(area, area)

    def area_coordinate(area: str) -> tuple[float, float] | None:
        """Get coordinate of area."""
        if (area_info := AREA_INFO.get(area)) is None:
            return None
        return area_info["lat"], area_info["lon"]

    def area_to_shelter_time(area: str) -> int | None:
        """Get time to shelter for area."""
        return AREA_TO_MIGUN_TIME.get(area)

    def area_to_distance(area: str, *args: Any) -> float | None:
        """Calculate distance of area from home or provided coordinate."""
        if (area_info := AREA_INFO.get(area)) is None:
            return None
        return distance_func(hass, area_info["lat"], area_info["lon"], *args)

    def area_distance_test(area: str, distance: float, *args: Any) -> bool:
        """Check if area is within the distance from home or provided coordinate."""
        actual = area_to_distance(area, *args)
        return actual is not None and actual <= distance

    def find_area_by_coordinate(lat: float, lon: float) -> str | None:
        """Find an area using lat/lon."""
        return find_area(lat, lon)

    def find_area_by_coordinate_filter(coordinate: tuple[float, float]) -> str | None:
        """Find an area using coordinate."""
        lat, lon = coordinate
        return find_area(lat, lon)

    original_template_environment_init = TemplateEnvironment.__init__

    def patch_environment(env: TemplateEnvironment) -> None:
        """Patch the template environment to add custom filters."""
        env.globals[AREAS_TEMPLATE_FUNCTION] = get_areas
        env.globals[DISTRICT_TEMPLATE_FUNCTION] = env.filters[
            DISTRICT_TEMPLATE_FUNCTION
        ] = area_to_district
        env.globals[COORDINATE_TEMPLATE_FUNCTION] = env.filters[
            COORDINATE_TEMPLATE_FUNCTION
        ] = area_coordinate
        env.globals[SHELTER_TEMPLATE_FUNCTION] = env.filters[
            SHELTER_TEMPLATE_FUNCTION
        ] = area_to_shelter_time
        env.globals[ICON_TEMPLATE_FUNCTION] = env.filters[ICON_TEMPLATE_FUNCTION] = (
            category_to_icon
        )
        env.globals[EMOJI_TEMPLATE_FUNCTION] = env.filters[EMOJI_TEMPLATE_FUNCTION] = (
            category_to_emoji
        )
        env.globals[DISTANCE_TEMPLATE_FUNCTION] = env.filters[
            DISTANCE_TEMPLATE_FUNCTION
        ] = area_to_distance
        env.globals[DISTANCE_TEST_TEMPLATE_FUNCTION] = env.tests[
            DISTANCE_TEST_TEMPLATE_FUNCTION
        ] = area_distance_test
        env.globals[FIND_AREA_TEMPLATE_FUNCTION] = find_area_by_coordinate
        env.filters[FIND_AREA_TEMPLATE_FUNCTION] = find_area_by_coordinate_filter

    def patched_init(
        self: TemplateEnvironment,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        original_template_environment_init(self, *args, **kwargs)
        patch_environment(self)

    # Patch "init" for new instances of TemplateEnvironment.
    TemplateEnvironment.__init__ = patched_init  # type: ignore  # noqa: PGH003

    # Patch the 3 existing instances of TemplateEnvironment.
    tpl = Template("", hass)
    for strict, limited in ((False, False), (True, False), (False, True)):
        tpl._strict = strict  # noqa: SLF001
        tpl._limited = limited  # noqa: SLF001
        if (env := tpl._env) is not None:  # noqa: SLF001
            patch_environment(env)
