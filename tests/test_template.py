"""Test custom templates."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    DOMAIN,
)
from custom_components.oref_alert.metadata.areas import AREAS
from custom_components.oref_alert.metadata.areas_and_groups import AREAS_AND_GROUPS


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


@pytest.mark.parametrize(
    ("template_str", "expected"),
    [
        ("{{ oref_district('פתח תקווה') }}", "דן"),
        ("{{ 'פתח תקווה' | oref_district }}", "דן"),
        ("{{ 'test' | oref_district }}", "test"),
        ("{{ oref_areas() }}", list(AREAS)),
        ("{{ oref_areas(True) }}", AREAS_AND_GROUPS),
        ("{{ oref_coordinate('פתח תקווה') }}", (32.084, 34.8878)),
        (
            "{{ 'תל אביב - מרכז העיר' | oref_coordinate }}",
            (32.0798, 34.7772),
        ),
        ("{{ 'test' | oref_coordinate }}", None),
        ("{{ oref_shelter('פתח תקווה') }}", 90),
        ("{{ 'בארי' | oref_shelter }}", 15),
        ("{{ 'test' | oref_shelter }}", None),
        ("{{ oref_icon(1) }}", "mdi:rocket-launch"),
        ("{{ 2 | oref_icon }}", "mdi:airplane-alert"),
        ("{{ oref_emoji(1) }}", "🚀"),
        ("{{ 2 | oref_emoji }}", "✈️"),
        ("{{ oref_distance('פתח תקווה') }}", 1.5687380000000002),
        ("{{ 'תל אביב - מרכז העיר' | oref_distance }}", 9.650307),
        (
            "{{ 'תל אביב - מרכז העיר' | oref_distance(31.78, 35.23) }}",
            54.208731,
        ),
        ("{{ oref_distance('test') }}", None),
        (
            "{{ oref_test_distance('תל אביב - מרכז העיר', 10) }}",
            True,
        ),
        ("{{ 'פתח תקווה' is oref_test_distance 2 }}", True),
        (
            "{{ ['פתח תקווה', 'תל אביב - מרכז העיר'] | "
            "select('oref_test_distance', 5, 32.072, 34.879) | list }}",
            ["פתח תקווה"],
        ),
        ("{{ oref_find_area(32.072, 34.879) }}", "פתח תקווה"),
        ("{{ oref_find_area(31.507, 34.460) }}", None),
    ],
    ids=[
        "district_direct",
        "district_pipe",
        "district_unknown",
        "areas_list",
        "areas_with_groups",
        "coordinate_direct",
        "coordinate_pipe",
        "coordinate_unknown",
        "shelter_direct",
        "shelter_pipe",
        "shelter_unknown",
        "icon_1",
        "icon_2",
        "emoji_1",
        "emoji_2",
        "distance_direct",
        "distance_pipe",
        "distance_with_override_coords",
        "distance_unknown",
        "distance_test_direct",
        "distance_test_is",
        "distance_test_select_list",
        "find_area_match",
        "find_area_none",
    ],
)
async def test_custom_templates(
    hass: HomeAssistant, template_str: str, expected: Any
) -> None:
    """Test custom templates."""
    assert Template(template_str, hass).async_render() == expected
