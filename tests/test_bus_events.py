"""The tests for the update_events file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    DOMAIN,
)

from .utils import mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import Event, HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

DEFAULT_OPTIONS = {CONF_AREAS: ["פתח תקווה"], CONF_ALERT_ACTIVE_DURATION: 10}


async def async_setup(
    hass: HomeAssistant, options: dict[str, Any] | None = None
) -> str:
    """Integration setup."""
    options = options or {}
    config_entry = MockConfigEntry(
        domain=DOMAIN, options={**DEFAULT_OPTIONS, **options}
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return config_entry.entry_id


async def async_shutdown(hass: HomeAssistant, config_id: str) -> None:
    """Shutdown by removing the integration."""
    assert await hass.config_entries.async_remove(config_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_alert_event(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test alert events."""
    hass.config.latitude = 32.072
    hass.config.longitude = 34.879
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")

    alerts: list[Event] = []
    records: list[Event] = []

    async def alert_listener(event: Event) -> None:
        alerts.append(event)

    async def record_listener(event: Event) -> None:
        records.append(event)

    hass.bus.async_listen(f"{DOMAIN}_event", alert_listener)
    hass.bus.async_listen(f"{DOMAIN}_record", record_listener)

    config_id = await async_setup(hass)

    assert len(alerts) == 1
    assert alerts[0].data == {
        "area": "בארי",
        "home_distance": 80.7,
        "latitude": 31.423811318545116,
        "longitude": 34.491396100227774,
        "category": 1,
        "title": "ירי רקטות וטילים",
        "icon": "mdi:rocket-launch",
        "emoji": "🚀",
        "channel": "website-history",
    }

    assert len(records) == 1
    assert records[0].data == {
        "area": "בארי",
        "home_distance": 80.7,
        "latitude": 31.423811318545116,
        "longitude": 34.491396100227774,
        "category": 1,
        "title": "ירי רקטות וטילים",
        "type": "alert",
        "icon": "mdi:rocket-launch",
        "emoji": "🚀",
        "channel": "website-history",
    }

    await async_shutdown(hass, config_id)


async def test_update_event(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test update event."""
    hass.config.latitude = 32.072
    hass.config.longitude = 34.879
    freezer.move_to("2025-04-26 03:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_update_history.json")

    updates: list[Event] = []
    records: list[Event] = []

    async def update_listener(event: Event) -> None:
        updates.append(event)

    async def record_listener(event: Event) -> None:
        records.append(event)

    hass.bus.async_listen(f"{DOMAIN}_update_event", update_listener)
    hass.bus.async_listen(f"{DOMAIN}_record", record_listener)

    config_id = await async_setup(hass)

    assert len(updates) == 1
    assert updates[0].data == {
        "area": "פתח תקווה",
        "home_distance": 2.5,
        "latitude": 32.09429109811987,
        "longitude": 34.8780320360819,
        "category": 13,
        "title": "ניתן לצאת מהמרחב המוגן",
        "icon": "mdi:message-alert",
        "emoji": "⚠",
        "channel": "website-history",
    }

    assert len(records) == 1
    assert records[0].data == {
        "area": "פתח תקווה",
        "home_distance": 2.5,
        "latitude": 32.09429109811987,
        "longitude": 34.8780320360819,
        "category": 13,
        "title": "ניתן לצאת מהמרחב המוגן",
        "type": "end",
        "icon": "mdi:message-alert",
        "emoji": "⚠",
        "channel": "website-history",
    }

    await async_shutdown(hass, config_id)


async def test_event_fired_once(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that update event is fired only once."""
    freezer.move_to("2025-04-26 03:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_update_history.json")

    events: list[Event] = []

    async def event_listener(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(f"{DOMAIN}_update_event", event_listener)

    config_id = await async_setup(hass)

    assert len(events) == 1

    freezer.tick(20)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert len(events) == 1

    await async_shutdown(hass, config_id)
