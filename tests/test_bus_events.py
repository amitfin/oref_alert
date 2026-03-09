"""The tests for the update_events file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

from homeassistant.const import ATTR_DATE
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import CONF_AREAS, DOMAIN

from .utils import mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import Event, HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

DEFAULT_OPTIONS = {CONF_AREAS: ["פתח תקווה"]}


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
        "area": "תל אביב - מרכז העיר",
        "home_distance": 9.2,
        "latitude": 32.079882706693276,
        "longitude": 34.781624113487126,
        "category": 13,
        "title": "ניתן לצאת מהמרחב המוגן",
        "icon": "mdi:message-alert",
        "emoji": "⚠",
        "channel": "website-history",
    }

    assert len(records) == 1
    assert records[0].data == {
        "area": "תל אביב - מרכז העיר",
        "home_distance": 9.2,
        "latitude": 32.079882706693276,
        "longitude": 34.781624113487126,
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


async def test_alert_history_save_restore_keeps_order(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test history save/restore preserves newest-first ordering."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "multi_alerts_history.json")

    config_id = await async_setup(hass)
    config_entry = hass.config_entries.async_get_entry(config_id)
    assert config_entry is not None
    bus_events = config_entry.runtime_data.bus_events

    saved: dict[str, list[dict[str, str | int]]] = {}

    async def save_side_effect(data: dict[str, list[dict[str, str | int]]]) -> None:
        saved.update(data)

    bus_events._store.async_save = AsyncMock(side_effect=save_side_effect)  # noqa: SLF001
    bus_events._store.async_load = AsyncMock(return_value=saved)  # noqa: SLF001

    await bus_events.async_save()

    # Clear in-memory state to validate restore path.
    bus_events.alert_history = bus_events.alert_history.__class__(ttl=60 * 24)
    bus_events._history_records = bus_events._history_records.__class__(ttl=60 * 24)  # noqa: SLF001
    bus_events._previous_items = bus_events._previous_items.__class__()  # noqa: SLF001

    await bus_events.async_restore()

    restored_history = list(bus_events.alert_history.items())
    assert [item["area"] for item in restored_history] == ["בארי", "נחל עוז"]
    assert [item[ATTR_DATE] for item in restored_history] == [
        "2023-10-07T06:30:00+03:00",
        "2023-10-07T06:28:00+03:00",
    ]

    # Persisted wire format is chronological to restore deterministically.
    assert [item["data"] for item in saved["records"]] == ["נחל עוז", "בארי"]

    await async_shutdown(hass, config_id)


async def test_restore_ignores_invalid_records_and_unknown_area_for_alert_history(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test restore robustness for invalid records and missing area metadata."""
    freezer.move_to("2023-10-07 06:31:00+03:00")
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    config_entry = hass.config_entries.async_get_entry(config_id)
    assert config_entry is not None
    bus_events = config_entry.runtime_data.bus_events

    bus_events._store.async_load = AsyncMock(  # noqa: SLF001
        return_value={
            "records": [
                {"bad": "record"},
                {
                    "alertDate": "2023-10-07 06:30:00",
                    "title": "ירי רקטות וטילים",
                    "data": "לא קיים",
                    "category": 1,
                    "channel": "website-history",
                },
            ]
        }
    )

    bus_events.alert_history = bus_events.alert_history.__class__(ttl=60 * 24)
    bus_events._history_records = bus_events._history_records.__class__(ttl=60 * 24)  # noqa: SLF001
    bus_events._previous_items = bus_events._previous_items.__class__()  # noqa: SLF001

    await bus_events.async_restore()

    assert list(bus_events.alert_history.items()) == []
    assert len(list(bus_events._history_records.items())) == 1  # noqa: SLF001
    assert len(list(bus_events._previous_items.items())) == 1  # noqa: SLF001

    await async_shutdown(hass, config_id)
