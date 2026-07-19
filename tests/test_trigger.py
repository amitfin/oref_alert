"""The tests for the trigger platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
import voluptuous as vol
from homeassistant.helpers import trigger as trigger_helper
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.oref_alert.const import (
    CATEGORY_FIELD,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    DOMAIN,
    OREF_ALERT_RECORD_EVENT,
    SYNTHETIC_ALERT_ACTION,
)
from custom_components.oref_alert.trigger import _attach_record_batch_listener

from .utils import fire_synthetic_alert, mock_urls

if TYPE_CHECKING:
    import asyncio

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

DEFAULT_OPTIONS = {CONF_AREAS: ["בארי"]}


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


async def _async_setup_automation(hass: HomeAssistant, trigger: dict[str, Any]) -> list:
    """Set up an automation with the given trigger and return its recorded calls."""
    calls = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "trigger": trigger,
                "action": {
                    "service": "test.automation",
                    "data_template": {
                        "areas": "{{ trigger.records | map(attribute='area') | list }}",
                        "types": "{{ trigger.records | map(attribute='type') | list }}",
                    },
                },
            }
        },
    )
    await hass.async_block_till_done()
    return calls


async def _async_fire_synthetic_alerts(
    hass: HomeAssistant, areas: list[str], category: int = 1
) -> None:
    """Fire synthetic alerts for multiple areas within a single coordinator refresh."""
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: areas, CONF_DURATION: 20, CATEGORY_FIELD: category},
        blocking=True,
    )
    await hass.async_block_till_done()


# --- oref_alert.home ---


async def test_home_trigger_matching_area(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home trigger fires for the areas configured on the integration."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.home"})

    await fire_synthetic_alert(hass, "בארי")

    assert len(calls) == 1
    assert calls[0].data["areas"] == ["בארי"]
    assert calls[0].data["types"] == ["alert"]

    await async_shutdown(hass, config_id)


async def test_home_trigger_non_matching_area(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home trigger does not fire for areas outside the integration's."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.home"})

    await fire_synthetic_alert(hass, "תל אביב - מרכז העיר")

    assert len(calls) == 0

    await async_shutdown(hass, config_id)


async def test_home_trigger_default_type_is_alert_only(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home trigger's default type filter excludes pre_alert."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.home"})

    await fire_synthetic_alert(hass, "בארי", category=14)

    assert len(calls) == 0

    await async_shutdown(hass, config_id)


async def test_home_trigger_explicit_type(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home trigger fires for an explicitly configured type."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass, {"trigger": "oref_alert.home", "type": "pre_alert"}
    )

    await fire_synthetic_alert(hass, "בארי", category=14)

    assert len(calls) == 1
    assert calls[0].data["types"] == ["pre_alert"]

    await async_shutdown(hass, config_id)


async def test_home_trigger_without_integration(hass: HomeAssistant) -> None:
    """Test the home trigger does not fire (nor err) with no integration configured."""
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.home"})

    hass.bus.async_fire(OREF_ALERT_RECORD_EVENT, {"area": "בארי", "type": "alert"})
    await hass.async_block_till_done()

    assert len(calls) == 0


# --- oref_alert.area ---


async def test_area_trigger_matching_area(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the area trigger fires for a matching area."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass, {"trigger": "oref_alert.area", "areas": "בארי"}
    )

    await fire_synthetic_alert(hass, "בארי")

    assert len(calls) == 1
    assert calls[0].data["areas"] == ["בארי"]
    assert calls[0].data["types"] == ["alert"]

    await async_shutdown(hass, config_id)


async def test_area_trigger_non_matching_area(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the area trigger does not fire for a non-matching area."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass, {"trigger": "oref_alert.area", "areas": "בארי"}
    )

    await fire_synthetic_alert(hass, "תל אביב - מרכז העיר")

    assert len(calls) == 0

    await async_shutdown(hass, config_id)


async def test_area_trigger_any_area_when_omitted(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the area trigger matches any area when areas is omitted."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.area"})

    # Not one of the integration's configured areas, proving there's no fallback to it.
    await fire_synthetic_alert(hass, "תל אביב - מרכז העיר")

    assert len(calls) == 1
    assert calls[0].data["areas"] == ["תל אביב - מרכז העיר"]

    await async_shutdown(hass, config_id)


async def test_area_trigger_default_type_is_alert_only(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the area trigger's default type filter excludes pre_alert."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass, {"trigger": "oref_alert.area", "areas": "בארי"}
    )

    await fire_synthetic_alert(hass, "בארי", category=14)

    assert len(calls) == 0

    await async_shutdown(hass, config_id)


async def test_area_trigger_explicit_type(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the area trigger fires for an explicitly configured type."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass, {"trigger": "oref_alert.area", "areas": "בארי", "type": "pre_alert"}
    )

    await fire_synthetic_alert(hass, "בארי", category=14)

    assert len(calls) == 1
    assert calls[0].data["types"] == ["pre_alert"]

    await async_shutdown(hass, config_id)


async def test_area_trigger_rejects_all_areas_alias(hass: HomeAssistant) -> None:
    """Test the schema rejects the all-areas aliases."""
    with pytest.raises(vol.Invalid):
        await trigger_helper.async_validate_trigger_config(
            hass, [{"platform": "oref_alert.area", "areas": "כל הארץ"}]
        )


async def test_area_trigger_any_area_without_integration(
    hass: HomeAssistant,
) -> None:
    """Test the area trigger fires for any area even without an integration."""
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.area"})

    hass.bus.async_fire(OREF_ALERT_RECORD_EVENT, {"area": "בארי", "type": "alert"})
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["areas"] == ["בארי"]


async def test_area_trigger_batches_records_from_the_same_update(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test simultaneous areas from one update fire the trigger only once."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.area"})

    # Both areas are added and refreshed together, so bus_events fires both
    # oref_alert_record events synchronously within the same coordinator update.
    await _async_fire_synthetic_alerts(hass, ["בארי", "תל אביב - מרכז העיר"])

    assert len(calls) == 1
    assert set(calls[0].data["areas"]) == {"בארי", "תל אביב - מרכז העיר"}

    await async_shutdown(hass, config_id)


# --- oref_alert.distance ---

# The real-world coordinate of "בארי", as published by add_synthetic_alert.
BAARI_LATITUDE = 31.423811318545116
BAARI_LONGITUDE = 34.491396100227774


async def test_distance_trigger_within_distance(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the distance trigger fires when the alert is close to zone.home."""
    hass.config.latitude = BAARI_LATITUDE
    hass.config.longitude = BAARI_LONGITUDE
    assert await async_setup_component(hass, "zone", {})
    await hass.async_block_till_done()

    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.distance"})

    await fire_synthetic_alert(hass, "בארי")

    assert len(calls) == 1
    assert calls[0].data["areas"] == ["בארי"]

    await async_shutdown(hass, config_id)


async def test_distance_trigger_outside_distance(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the distance trigger does not fire when the alert is far from zone.home."""
    assert await async_setup_component(hass, "zone", {})
    await hass.async_block_till_done()

    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.distance"})

    await fire_synthetic_alert(hass, "בארי")

    assert len(calls) == 0

    await async_shutdown(hass, config_id)


async def test_distance_trigger_default_type_is_alert_only(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the distance trigger's default type filter excludes pre_alert."""
    hass.config.latitude = BAARI_LATITUDE
    hass.config.longitude = BAARI_LONGITUDE
    assert await async_setup_component(hass, "zone", {})
    await hass.async_block_till_done()

    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.distance"})

    await fire_synthetic_alert(hass, "בארי", category=14)

    assert len(calls) == 0

    await async_shutdown(hass, config_id)


async def test_distance_trigger_explicit_type(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the distance trigger fires for an explicitly configured type."""
    hass.config.latitude = BAARI_LATITUDE
    hass.config.longitude = BAARI_LONGITUDE
    assert await async_setup_component(hass, "zone", {})
    await hass.async_block_till_done()

    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass, {"trigger": "oref_alert.distance", "type": "pre_alert"}
    )

    await fire_synthetic_alert(hass, "בארי", category=14)

    assert len(calls) == 1
    assert calls[0].data["types"] == ["pre_alert"]

    await async_shutdown(hass, config_id)


async def test_distance_trigger_explicit_location_and_distance(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the distance trigger with an explicit device_tracker and distance."""
    hass.states.async_set(
        "device_tracker.phone",
        "home",
        {"latitude": BAARI_LATITUDE, "longitude": BAARI_LONGITUDE},
    )

    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass,
        {
            "trigger": "oref_alert.distance",
            "distance": 1,
            "location": "device_tracker.phone",
        },
    )

    await fire_synthetic_alert(hass, "בארי")

    assert len(calls) == 1

    await async_shutdown(hass, config_id)


async def test_distance_trigger_missing_location_entity(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the distance trigger does not fire (nor err) for a missing location."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass,
        {"trigger": "oref_alert.distance", "location": "device_tracker.missing"},
    )

    await fire_synthetic_alert(hass, "בארי")

    assert len(calls) == 0

    await async_shutdown(hass, config_id)


async def test_distance_trigger_ignores_record_without_coordinates(
    hass: HomeAssistant,
) -> None:
    """Test the distance trigger does not fire (nor err) for a bad record."""
    assert await async_setup_component(hass, "zone", {})
    await hass.async_block_till_done()
    calls = await _async_setup_automation(hass, {"trigger": "oref_alert.distance"})

    hass.bus.async_fire(OREF_ALERT_RECORD_EVENT, {"area": "בארי", "type": "alert"})
    await hass.async_block_till_done()

    assert len(calls) == 0


async def test_distance_trigger_rejects_non_location_domain(
    hass: HomeAssistant,
) -> None:
    """Test the schema rejects a location entity outside zone/device_tracker/person."""
    with pytest.raises(vol.Invalid):
        await trigger_helper.async_validate_trigger_config(
            hass,
            [{"platform": "oref_alert.distance", "location": "sensor.temperature"}],
        )


async def test_distance_trigger_batches_records_from_the_same_update(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test simultaneous nearby areas from one update fire the trigger only once."""
    hass.config.latitude = BAARI_LATITUDE
    hass.config.longitude = BAARI_LONGITUDE
    assert await async_setup_component(hass, "zone", {})
    await hass.async_block_till_done()

    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    calls = await _async_setup_automation(
        hass, {"trigger": "oref_alert.distance", "distance": 1000}
    )

    await _async_fire_synthetic_alerts(hass, ["בארי", "תל אביב - מרכז העיר"])

    assert len(calls) == 1
    assert set(calls[0].data["areas"]) == {"בארי", "תל אביב - מרכז העיר"}

    await async_shutdown(hass, config_id)


async def test_batch_listener_cancels_pending_flush_on_unsub(
    hass: HomeAssistant,
) -> None:
    """Test unsub cancels a not-yet-run flush so it can't fire stale."""
    calls: list[dict[str, Any]] = []

    def run_action(*args: Any, **_kwargs: Any) -> asyncio.Task[Any]:
        """Record the payload, matching the TriggerActionRunner protocol."""
        calls.append(args[0])
        return cast("asyncio.Task[Any]", None)

    unsub = _attach_record_batch_listener(hass, lambda _data: True, run_action)

    hass.bus.async_fire(OREF_ALERT_RECORD_EVENT, {"area": "בארי", "type": "alert"})
    unsub()
    await hass.async_block_till_done()

    assert calls == []
