"""Test custom templates."""

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.const import ATTR_DATE
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert.const import (
    CONF_AREAS,
    DOMAIN,
)
from custom_components.oref_alert.metadata.area_to_polygon import init_area_to_polygon
from custom_components.oref_alert.metadata.areas import AREAS
from custom_components.oref_alert.metadata.areas_and_groups import AREAS_AND_GROUPS

from .utils import mock_urls

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

_OREF_ALERTS = [
    {
        "area": "בארי",
        "home_distance": 80.7,
        "latitude": 31.423811318545116,
        "longitude": 34.491396100227774,
        "category": 1,
        "title": "ירי רקטות וטילים",
        "icon": "mdi:rocket-launch",
        "emoji": "🚀",
        "channel": "website-history",
        ATTR_DATE: "2023-10-07T06:30:00+03:00",
    },
    {
        "area": "נחל עוז",
        "home_distance": 75.7,
        "latitude": 31.472169943762964,
        "longitude": 34.4983670455394,
        "category": 1,
        "title": "ירי רקטות וטילים",
        "icon": "mdi:rocket-launch",
        "emoji": "🚀",
        "channel": "website-history",
        ATTR_DATE: "2023-10-07T06:28:00+03:00",
    },
]


async def async_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker | None = None
) -> str:
    """Integration setup."""
    if aioclient_mock:
        mock_urls(aioclient_mock, None, "multi_alerts_history.json")
    hass.config.latitude = 32.072
    hass.config.longitude = 34.879
    config_entry = MockConfigEntry(domain=DOMAIN, options={CONF_AREAS: ["בארי"]})
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return config_entry.entry_id


async def async_shutdown(hass: HomeAssistant, config_id: str) -> None:
    """Shutdown by removing the integration."""
    assert await hass.config_entries.async_remove(config_id)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.fixture
async def load_oref_integration(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> AsyncGenerator[None]:
    """Prepare the test environment."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    config_id = await async_setup(hass, aioclient_mock)
    yield
    await async_shutdown(hass, config_id)


@pytest.mark.parametrize(
    ("template_str", "expected"),
    [
        ("{{ oref_district('פתח תקווה') }}", "ירקון"),
        ("{{ 'פתח תקווה' | oref_district }}", "ירקון"),
        ("{{ 'test' | oref_district }}", "test"),
        ("{{ oref_areas() }}", list(AREAS)),
        ("{{ oref_areas | list }}", list(AREAS)),
        ("{{ oref_areas(True) }}", AREAS_AND_GROUPS),
        ("{{ oref_alerts() | list }}", _OREF_ALERTS),
        ("{{ oref_alerts | list }}", _OREF_ALERTS),
        ("{{ oref_coordinate('פתח תקווה') }}", (32.09429109811987, 34.8780320360819)),
        (
            "{{ 'תל אביב - מרכז העיר' | oref_coordinate }}",
            (32.079882706693276, 34.781624113487126),
        ),
        ("{{ 'test' | oref_coordinate }}", None),
        ("{{ oref_shelter('פתח תקווה') }}", 90),
        ("{{ 'בארי' | oref_shelter }}", 15),
        ("{{ 'test' | oref_shelter }}", None),
        ("{{ oref_icon(1) }}", "mdi:rocket-launch"),
        ("{{ 2 | oref_icon }}", "mdi:airplane-alert"),
        ("{{ oref_emoji(1) }}", "🚀"),
        ("{{ 2 | oref_emoji }}", "✈️"),
        ("{{ oref_distance('פתח תקווה') }}", 2.47351),
        ("{{ 'תל אביב - מרכז העיר' | oref_distance }}", 9.23522),
        (
            "{{ 'תל אביב - מרכז העיר' | oref_distance(31.78, 35.23) }}",
            53.884525,
        ),
        ("{{ oref_distance('test') }}", None),
        (
            "{{ oref_test_distance('תל אביב - מרכז העיר', 10) }}",
            True,
        ),
        ("{{ 'פתח תקווה' is oref_test_distance 3 }}", True),
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
        ("{{ oref_polygon(none) }}", None),
        ("{{ oref_polygon('unknown') }}", None),
    ],
    ids=[
        "district_func",
        "district_filter",
        "district_unknown",
        "areas_list",
        "areas_iterable",
        "areas_with_groups",
        "alerts_func",
        "alerts",
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
        "polygon_none",
        "polygon_unknown",
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


async def test_polygon(
    hass: HomeAssistant,
    load_oref_integration: None,  # noqa: ARG001
) -> None:
    """Test oref_polygon."""
    polygons = await init_area_to_polygon()
    assert (
        Template("{{ oref_polygon('פתח תקווה') }}", hass).async_render()
        == polygons["פתח תקווה"]
    )
    assert (
        Template("{{ 'גבעת שמואל' | oref_polygon }}", hass).async_render()
        == polygons["גבעת שמואל"]
    )


@pytest.mark.allowed_logs(["Template variable error:"])
def test_limited_environment(hass: HomeAssistant, load_oref_integration: None) -> None:  # noqa: ARG001
    """Test limited environment."""
    statement = "{{ oref_find_area(32.072, 34.879) == 'פתח תקווה' }}"

    assert Template(statement, hass).async_render() is True

    with pytest.raises(
        TemplateError, match="UndefinedError: 'oref_find_area' is undefined"
    ):
        Template(statement, hass).async_render(limited=True)

    with pytest.raises(
        TemplateError, match="UndefinedError: 'oref_find_area' is undefined"
    ):
        Template(statement, hass).async_render(limited=True, log_fn=lambda _1, _2: None)


@pytest.mark.allowed_logs(["Template variable error:"])
async def test_unload(hass: HomeAssistant) -> None:
    """Test no template extensions after unload."""
    statement = "{{ oref_areas() | length > 0 }}"
    config_id = await async_setup(hass)
    assert Template(statement, hass).async_render() is True
    await async_shutdown(hass, config_id)
    with pytest.raises(
        TemplateError, match="UndefinedError: 'oref_areas' is undefined"
    ):
        Template(statement, hass).async_render()
