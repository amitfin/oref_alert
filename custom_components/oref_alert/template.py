"""Inject template extensions to the Home Assistant instance."""

# The injection logic is based on:
# https://github.com/PiotrMachowski/Home-Assistant-custom-components-Custom-Templates/blob/master/custom_components/custom_templates/__init__.py

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template, TemplateEnvironment

from .const import DISTRICT_TEMPLATE_FUNCTION
from .metadata.area_to_district import AREA_TO_DISTRICT


def area_to_district(area: str) -> str:
    """Convert area to district."""
    return AREA_TO_DISTRICT.get(area, area)


def inject_template_extensions(hass: HomeAssistant) -> None:
    """Inject template extension to the Home Assistant instance."""
    original_template_environment_init = TemplateEnvironment.__init__

    def patch_environment(env: TemplateEnvironment) -> None:
        """Patch the template environment to add custom filters."""
        env.globals[DISTRICT_TEMPLATE_FUNCTION] = env.filters[
            DISTRICT_TEMPLATE_FUNCTION
        ] = area_to_district

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
