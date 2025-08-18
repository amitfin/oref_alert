"""Inject template extensions to the Home Assistant instance."""

# The injection logic is based on:
# https://github.com/PiotrMachowski/Home-Assistant-custom-components-Custom-Templates/blob/master/custom_components/custom_templates/__init__.py
from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.template import (
    Template,
    TemplateEnvironment,
)
from homeassistant.helpers.template import (
    distance as distance_func,
)

from . import const
from .categories import category_to_emoji, category_to_icon
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
from .metadata.area_info import AREA_INFO
from .metadata.area_to_district import AREA_TO_DISTRICT
from .metadata.area_to_migun_time import AREA_TO_MIGUN_TIME
from .metadata.area_to_polygon import (
    find_area,
    init_area_to_polygon,
)
from .metadata.areas import AREAS
from .metadata.areas_and_groups import AREAS_AND_GROUPS

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

_template_environment_init_signature = inspect.signature(TemplateEnvironment.__init__)


async def inject_template_extensions(hass: HomeAssistant) -> Callable[[], None]:  # noqa: PLR0915
    """Inject template extension to the Home Assistant instance."""
    template_environment_init = TemplateEnvironment.__init__

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

    def patch_environment(env: TemplateEnvironment, limited: bool) -> None:  # noqa: FBT001
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
        if not limited:
            env.globals[FIND_AREA_TEMPLATE_FUNCTION] = find_area_by_coordinate
            env.filters[FIND_AREA_TEMPLATE_FUNCTION] = find_area_by_coordinate_filter

    def revert_environment(env: TemplateEnvironment, *_: Any) -> None:
        """Remove template extensions."""
        functions = [
            function
            for function in dir(const)
            if function.endswith("TEMPLATE_FUNCTION")
        ]
        for extensions in (env.globals, env.filters, env.tests):
            for function in functions:
                extensions.pop(getattr(const, function), None)

    def patched_init(
        self: TemplateEnvironment,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        template_environment_init(self, *args, **kwargs)

        params = _template_environment_init_signature.bind_partial(
            self, *args, **kwargs
        )
        params.apply_defaults()

        patch_environment(self, params.arguments.get("limited", False))

    def fix_cached_environments(
        fix_function: Callable[[TemplateEnvironment, bool], None],
    ) -> None:
        """Patch the 3 existing instances of TemplateEnvironment."""
        template = Template("", hass)
        for limited, strict in ((False, False), (True, False), (False, True)):
            template._limited = limited  # noqa: SLF001
            template._strict = strict  # noqa: SLF001
            if (env := template._env) is not None:  # noqa: SLF001
                fix_function(env, limited)

    # Patch "init" for new instances of TemplateEnvironment.
    TemplateEnvironment.__init__ = patched_init  # type: ignore  # noqa: PGH003

    # Patch existing instances of TemplateEnvironment.
    fix_cached_environments(patch_environment)

    def unload_template_extensions() -> None:
        """Remove template extensions."""
        TemplateEnvironment.__init__ = template_environment_init  # type: ignore[method-assign]
        fix_cached_environments(revert_environment)

    return unload_template_extensions
