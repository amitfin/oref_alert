"""The tests for the sensor file."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_UNKNOWN, Platform
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    ADD_SENSOR_ACTION,
    ATTR_ALERT,
    ATTR_AREA,
    ATTR_DISPLAY,
    ATTR_RECORD,
    ATTR_TIME_TO_SHELTER,
    CONF_AREAS,
    DOMAIN,
    IST,
    OREF_ALERT_UNIQUE_ID,
    REMOVE_SENSOR_ACTION,
    TIME_TO_SHELTER_ID_SUFFIX,
    Record,
    RecordAndMetadata,
)
from custom_components.oref_alert.coordinator import OrefAlertCoordinatorData
from custom_components.oref_alert.records_schema import RecordType

from .utils import load_json_fixture, mock_urls, refresh_coordinator

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

DEFAULT_OPTIONS = {CONF_AREAS: ["בארי"]}
TIME_TO_SHELTER_ENTITY_ID = (
    f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}_{TIME_TO_SHELTER_ID_SUFFIX}"
)
STATUS_ENTITY_ID = f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}"


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


async def test_time_to_shelter_state(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test entity state."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "multi_alerts_real_time.json", "multi_alerts_history.json"
    )

    config_id = await async_setup(hass)

    time_to_shelter = 15
    state = hass.states.get(TIME_TO_SHELTER_ENTITY_ID)
    assert state is not None
    assert state.state == str(time_to_shelter)
    assert state.name == "Oref Alert Time To Shelter"
    assert (
        state.attributes[ATTR_ALERT]
        == load_json_fixture("single_alert_history.json", "website-history")[0]
    )
    assert state.attributes[ATTR_DISPLAY] == f"00:{time_to_shelter:02}"

    for _ in range(100):
        freezer.tick()
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        time_to_shelter -= 1
        state = hass.states.get(TIME_TO_SHELTER_ENTITY_ID)
        assert state is not None
        assert state.state == (
            str(time_to_shelter) if time_to_shelter > -60 else STATE_UNKNOWN
        )
        if time_to_shelter >= 0:
            assert (
                state.attributes[ATTR_DISPLAY]
                == f"{time_to_shelter // 60:02}:{time_to_shelter % 60:02}"
            )
        elif time_to_shelter > -60:
            assert (
                state.attributes[ATTR_DISPLAY]
                == f"-{abs(time_to_shelter) // 60:02}:{abs(time_to_shelter) % 60:02}"
            )
        else:
            assert state.attributes[ATTR_DISPLAY] is None

    await async_shutdown(hass, config_id)


async def test_time_to_shelter_not_going_back(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test time to shelter is not going back despite earlier timestamp in history."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)

    config_id = await async_setup(hass, {CONF_AREAS: ["תל אביב - מרכז העיר"]})

    state = hass.states.get(TIME_TO_SHELTER_ENTITY_ID)
    assert state is not None
    assert state.state == "90"

    mock_urls(aioclient_mock, None, "history_same_as_real_time.json")
    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(TIME_TO_SHELTER_ENTITY_ID)
    assert state is not None
    assert state.state == "80"

    await async_shutdown(hass, config_id)


async def test_time_to_shelter_attributes_no_alert(
    hass: HomeAssistant,
) -> None:
    """Test attributes when there is no alert."""
    config_id = await async_setup(hass)
    state = hass.states.get(TIME_TO_SHELTER_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_AREA] == "בארי"
    assert state.attributes[ATTR_TIME_TO_SHELTER] == 15
    assert state.attributes[ATTR_ALERT] is None
    assert state.attributes[ATTR_DISPLAY] is None
    await async_shutdown(hass, config_id)


async def test_status_state_no_alert(
    hass: HomeAssistant,
) -> None:
    """Test status sensor state when no alert exists."""
    config_id = await async_setup(hass)
    state = hass.states.get(STATUS_ENTITY_ID)
    assert state is not None
    assert state.state == "ok"
    assert state.name == "Oref Alert"
    assert state.attributes[ATTR_AREA] == "בארי"
    assert state.attributes[ATTR_RECORD] is None
    await async_shutdown(hass, config_id)


async def test_status_state_transition_and_cache(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test status transitions and cached latest record behavior."""
    freezer.move_to("2025-01-01 12:00:00+03:00")
    config_id = await async_setup(hass)
    config = hass.config_entries.async_get_entry(config_id)
    assert config is not None
    coordinator = config.runtime_data.coordinator

    pre_alert_record = Record(
        data="בארי",
        category=14,
        channel="website-history",
        alertDate="2025-01-01 11:59:30",
        title="",
    )
    pre_alert_metadata = RecordAndMetadata(
        raw=pre_alert_record,
        raw_dict=asdict(pre_alert_record),
        time=dt_util.parse_datetime(
            pre_alert_record.alertDate, raise_on_error=True
        ).replace(tzinfo=IST),
        record_type=RecordType.PRE_ALERT,
        expire=dt_util.parse_datetime(
            "2025-01-01 12:19:30", raise_on_error=True
        ).replace(tzinfo=IST),
    )
    coordinator.data = OrefAlertCoordinatorData({"בארי": pre_alert_metadata})
    coordinator.async_update_listeners()
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(STATUS_ENTITY_ID)
    assert state is not None
    assert state.state == RecordType.PRE_ALERT
    assert state.attributes[ATTR_RECORD] == {
        "data": "בארי",
        "category": 14,
        "channel": "website-history",
        "alertDate": "2025-01-01 11:59:30",
        "title": "",
    }

    alert_record = Record(
        data="בארי",
        category=1,
        channel="website-history",
        alertDate="2025-01-01 11:59:40",
        title="",
    )
    alert_metadata = RecordAndMetadata(
        raw=alert_record,
        raw_dict=asdict(alert_record),
        time=dt_util.parse_datetime(
            alert_record.alertDate, raise_on_error=True
        ).replace(tzinfo=IST),
        record_type=RecordType.ALERT,
        expire=dt_util.parse_datetime(
            "2025-01-01 23:59:40", raise_on_error=True
        ).replace(tzinfo=IST),
    )
    coordinator.data = OrefAlertCoordinatorData({"בארי": alert_metadata})
    coordinator.async_update_listeners()
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(STATUS_ENTITY_ID)
    assert state is not None
    assert state.state == RecordType.ALERT
    assert state.attributes[ATTR_RECORD] == {
        "data": "בארי",
        "category": 1,
        "channel": "website-history",
        "alertDate": "2025-01-01 11:59:40",
        "title": "",
    }

    coordinator.data = OrefAlertCoordinatorData({})
    coordinator.async_update_listeners()
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(STATUS_ENTITY_ID)
    assert state is not None
    assert state.state == "ok"
    assert state.attributes[ATTR_RECORD] is None

    await async_shutdown(hass, config_id)


async def test_status_state_end_record(
    hass: HomeAssistant,
) -> None:
    """Test status returns OK for END records."""
    config_id = await async_setup(hass)
    config = hass.config_entries.async_get_entry(config_id)
    assert config is not None
    coordinator = config.runtime_data.coordinator

    end_record = Record(
        data="בארי",
        category=13,
        channel="website-history",
        alertDate="2025-01-01 11:59:00",
        title="",
    )
    end_metadata = RecordAndMetadata(
        raw=end_record,
        raw_dict=asdict(end_record),
        time=dt_util.parse_datetime(end_record.alertDate, raise_on_error=True).replace(
            tzinfo=IST
        ),
        record_type=RecordType.END,
        expire=None,
    )
    coordinator.data = OrefAlertCoordinatorData({"בארי": end_metadata})
    coordinator.async_update_listeners()
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(STATUS_ENTITY_ID)
    assert state is not None
    assert state.state == "ok"
    assert state.attributes[ATTR_RECORD] == {
        "data": "בארי",
        "category": 13,
        "channel": "website-history",
        "alertDate": "2025-01-01 11:59:00",
        "title": "",
    }

    await async_shutdown(hass, config_id)


async def test_status_state_expired_pre_alert(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test status returns OK for expired pre_alert records."""
    freezer.move_to("2025-01-01 12:00:00+02:00")
    config_id = await async_setup(hass)
    config = hass.config_entries.async_get_entry(config_id)
    assert config is not None
    coordinator = config.runtime_data.coordinator

    old_pre_alert_record = Record(
        data="בארי",
        category=14,
        channel="website-history",
        alertDate="2025-01-01 11:30:00",
        title="",
    )
    old_metadata = RecordAndMetadata(
        raw=old_pre_alert_record,
        raw_dict=asdict(old_pre_alert_record),
        time=dt_util.parse_datetime(
            old_pre_alert_record.alertDate, raise_on_error=True
        ).replace(tzinfo=IST),
        record_type=RecordType.PRE_ALERT,
        expire=dt_util.parse_datetime(
            "2025-01-01 11:50:00", raise_on_error=True
        ).replace(tzinfo=IST),
    )
    coordinator.data = OrefAlertCoordinatorData({"בארי": old_metadata})
    coordinator.async_update_listeners()
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(STATUS_ENTITY_ID)
    assert state is not None
    assert state.state == RecordType.PRE_ALERT
    assert state.attributes[ATTR_RECORD] == {
        "data": "בארי",
        "category": 14,
        "channel": "website-history",
        "alertDate": "2025-01-01 11:30:00",
        "title": "",
    }

    await async_shutdown(hass, config_id)


async def test_alert_expires_after_180_minutes_end_to_end(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test alert expiration through coordinator refresh and sensor state updates."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")
    alert = load_json_fixture("single_alert_history.json", "website-history")[0]

    config_id = await async_setup(hass)

    status = hass.states.get(STATUS_ENTITY_ID)
    assert status is not None
    assert status.state == RecordType.ALERT
    assert status.attributes[ATTR_RECORD] == alert

    freezer.tick(180 * 60 + 1)
    await refresh_coordinator(hass, config_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    status = hass.states.get(STATUS_ENTITY_ID)
    assert status is not None
    assert status.state == "ok"
    assert status.attributes[ATTR_RECORD] is None

    await async_shutdown(hass, config_id)


async def test_no_entity_for_multi_areas(
    hass: HomeAssistant,
) -> None:
    """Test no entity is created for config with multi areas."""
    config_id = await async_setup(hass, {CONF_AREAS: ["תל אביב - כל האזורים"]})
    assert not hass.states.async_entity_ids(Platform.SENSOR)
    await async_shutdown(hass, config_id)


async def test_additional_sensor(
    hass: HomeAssistant,
) -> None:
    """Test additional sensor."""
    config_id = await async_setup(hass, {CONF_AREAS: ["תל אביב - כל האזורים"]})
    await hass.services.async_call(
        DOMAIN,
        ADD_SENSOR_ACTION,
        {CONF_NAME: "Test", CONF_AREAS: ["רעננה"]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    sensors = hass.states.async_entity_ids(Platform.SENSOR)
    assert len(sensors) == 2
    for entity_id, name in (
        (
            f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}_test_{TIME_TO_SHELTER_ID_SUFFIX}",
            "Oref Alert Test Time To Shelter",
        ),
        (
            f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}_test",
            "Oref Alert Test",
        ),
    ):
        assert entity_id in sensors
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.name == name
        assert state.attributes[ATTR_AREA] == "רעננה"
    await async_shutdown(hass, config_id)


async def test_remove_sensors(
    hass: HomeAssistant,
) -> None:
    """Test removing sensors from entity registry."""
    config_id = await async_setup(hass)
    await hass.services.async_call(
        DOMAIN,
        ADD_SENSOR_ACTION,
        {CONF_NAME: "test", CONF_AREAS: ["רעננה"]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    # There are 3 binary sensors: default, all, test
    assert len(hass.states.async_entity_ids(Platform.BINARY_SENSOR)) == 3
    # There are 4 sensors: (time-to-shelter, status) * (default, test)
    assert len(hass.states.async_entity_ids(Platform.SENSOR)) == 4
    await hass.services.async_call(
        DOMAIN,
        REMOVE_SENSOR_ACTION,
        {CONF_ENTITY_ID: "binary_sensor.oref_alert_test"},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(hass.states.async_entity_ids(Platform.BINARY_SENSOR)) == 2
    assert len(hass.states.async_entity_ids(Platform.SENSOR)) == 2
    await async_shutdown(hass, config_id)


@pytest.mark.slow
async def test_all_areas_alert(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test alert with all areas alias."""
    freezer.move_to("2025-06-13 03:00:00+03:00")
    mock_urls(aioclient_mock, None, "single_all_areas_alert_history.json")
    alert = load_json_fixture("single_all_areas_alert_history.json", "website-history")[
        0
    ]

    config_id = await async_setup(hass)

    state = hass.states.get(TIME_TO_SHELTER_ENTITY_ID)
    assert state is not None
    assert state.state == "15"
    assert state.attributes[ATTR_ALERT] == alert

    state = hass.states.get(STATUS_ENTITY_ID)
    assert state is not None
    assert state.state == "alert"
    assert state.attributes[ATTR_RECORD] == alert

    await async_shutdown(hass, config_id)
