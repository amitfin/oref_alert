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


@pytest.fixture
async def load_oref_integration(hass: HomeAssistant) -> AsyncGenerator[None]:
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
        (
            "{{ [oref_coordinate('פתח תקווה'), (32.0798, 34.7772)] | "
            "map('oref_find_area') | list }}",
            ["פתח תקווה", "תל אביב - מרכז העיר"],
        ),
        ("{{ oref_find_area(31.507, 34.460) }}", None),
    ],
    ids=[
        "district_func",
        "district_filter",
        "district_unknown",
        "areas_list",
        "areas_with_groups",
        "coordinate_func",
        "coordinate_filter",
        "coordinate_unknown",
        "shelter_func",
        "shelter_filter",
        "shelter_unknown",
        "icon_1",
        "icon_2",
        "emoji_1",
        "emoji_2",
        "distance_func",
        "distance_filter",
        "distance_with_override_coords",
        "distance_unknown",
        "distance_test_func",
        "distance_test_is",
        "distance_test_select_list",
        "find_area_func",
        "find_area_filter",
        "find_area_none",
    ],
)
def test_custom_templates(
    hass: HomeAssistant,
    load_oref_integration: None,  # noqa: ARG001
    template_str: str,
    expected: Any,
) -> None:
    """Test custom templates."""
    assert Template(template_str, hass).async_render() == expected


def test_limited_environment(hass: HomeAssistant, load_oref_integration: None) -> None:  # noqa: ARG001
    """Test limited environment."""
    statement = "{{ oref_find_area(32.072, 34.879) == 'פתח תקווה' }}"

    assert Template(statement, hass).async_render() is True

    with pytest.raises(
        Exception, match="UndefinedError: 'oref_find_area' is undefined"
    ):
        Template(statement, hass).async_render(limited=True)

    with pytest.raises(
        Exception, match="UndefinedError: 'oref_find_area' is undefined"
    ):
        Template(statement, hass).async_render(limited=True, log_fn=lambda _1, _2: None)


async def test_unload(hass: HomeAssistant) -> None:
    """Test no template extensions after unload."""
    statement = "{{ oref_areas() | length > 0 }}"
    config_id = await async_setup(hass)
    assert Template(statement, hass).async_render() is True
    await async_shutdown(hass, config_id)
    with pytest.raises(Exception, match="UndefinedError: 'oref_areas' is undefined"):
        Template(statement, hass).async_render()
