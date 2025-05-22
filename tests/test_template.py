"""Test custom templates."""

from collections.abc import AsyncGenerator

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    DISTANCE_TEMPLATE_FUNCTION,
    DISTANCE_TEST_TEMPLATE_FUNCTION,
    DISTRICT_TEMPLATE_FUNCTION,
    DOMAIN,
    EMOJI_TEMPLATE_FUNCTION,
    ICON_TEMPLATE_FUNCTION,
)


async def async_setup(hass: HomeAssistant) -> str:
    """Integration setup."""
    hass.config.latitude = 32.072
    hass.config.longitude = 34.879
    config_entry = MockConfigEntry(
        domain=DOMAIN, options={CONF_AREAS: ["בארי"], CONF_ALERT_ACTIVE_DURATION: 10}
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return config_entry.entry_id


async def async_shutdown(hass: HomeAssistant, config_id: str) -> None:
    """Shutdown by removing the integration."""
    assert await hass.config_entries.async_remove(config_id)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.fixture(autouse=True)
async def async_load_oref_integration(hass: HomeAssistant) -> AsyncGenerator[None]:
    """Prepare the test environment."""
    config_id = await async_setup(hass)
    yield
    await async_shutdown(hass, config_id)


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


async def test_icon(hass: HomeAssistant) -> None:
    """Test custom template category to icon."""
    assert (
        Template(f"{{{{ {ICON_TEMPLATE_FUNCTION}(1) }}}}", hass).async_render(
            parse_result=False
        )
        == "mdi:rocket-launch"
    )
    assert (
        Template(f"{{{{ 2 | {ICON_TEMPLATE_FUNCTION} }}}}", hass).async_render(
            parse_result=False
        )
        == "mdi:airplane-alert"
    )


async def test_emoji(hass: HomeAssistant) -> None:
    """Test custom template category to emoji."""
    assert (
        Template(f"{{{{ {EMOJI_TEMPLATE_FUNCTION}(1) }}}}", hass).async_render(
            parse_result=False
        )
        == "🚀"
    )
    assert (
        Template(f"{{{{ 2 | {EMOJI_TEMPLATE_FUNCTION} }}}}", hass).async_render(
            parse_result=False
        )
        == "✈️"
    )


async def test_distance(hass: HomeAssistant) -> None:
    """Test custom template area to distance."""
    assert (
        Template(
            f"{{{{ {DISTANCE_TEMPLATE_FUNCTION}('פתח תקווה') }}}}", hass
        ).async_render()
        == 1.5687380000000002
    )
    assert (
        Template(
            f"{{{{ 'תל אביב - מרכז העיר' | {DISTANCE_TEMPLATE_FUNCTION} }}}}", hass
        ).async_render()
        == 9.650307
    )
    assert (
        Template(
            (
                "{{ 'תל אביב - מרכז העיר'"
                f" | {DISTANCE_TEMPLATE_FUNCTION}(31.78, 35.23) }}}}"
            ),
            hass,
        ).async_render()
        == 54.208731
    )
    assert (
        Template(f"{{{{ {DISTANCE_TEMPLATE_FUNCTION}('test') }}}}", hass).async_render()
        == -1
    )


async def test_distance_check(hass: HomeAssistant) -> None:
    """Test custom template distance test."""
    assert (
        Template(
            f"{{{{ {DISTANCE_TEST_TEMPLATE_FUNCTION}('תל אביב - מרכז העיר', 10) }}}}",
            hass,
        ).async_render()
        is True
    )
    assert (
        Template(
            f"{{{{ 'פתח תקווה' is {DISTANCE_TEST_TEMPLATE_FUNCTION} 2 }}}}",
            hass,
        ).async_render()
        is True
    )
    assert (
        Template(
            "{{ ['פתח תקווה', 'תל אביב - מרכז העיר'] | "
            f"select('{DISTANCE_TEST_TEMPLATE_FUNCTION}', 5) | list }}}}",
            hass,
        ).async_render(parse_result=False)
        == "['פתח תקווה']"
    )
