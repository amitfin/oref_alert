"""Test custom templates."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from custom_components.oref_alert.const import DISTRICT_TEMPLATE_FUNCTION


async def test_function(hass: HomeAssistant) -> None:
    """Test custom template function."""
    assert (
        Template(
            f"{{{{ {DISTRICT_TEMPLATE_FUNCTION}('פתח תקווה') }}}}", hass
        ).async_render(parse_result=False)
        == "דן"
    )


async def test_filter(hass: HomeAssistant) -> None:
    """Test custom template filter."""
    assert (
        Template(
            f"{{{{ 'פתח תקווה' | {DISTRICT_TEMPLATE_FUNCTION} }}}}", hass
        ).async_render(parse_result=False)
        == "דן"
    )


async def test_unknown_area(hass: HomeAssistant) -> None:
    """Test custom template with unknown area."""
    assert (
        Template(f"{{{{ 'test' | {DISTRICT_TEMPLATE_FUNCTION} }}}}", hass).async_render(
            parse_result=False
        )
        == "test"
    )
