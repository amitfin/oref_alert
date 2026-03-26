"""The tests for the init file."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.const import (
    ATTR_DATE,
    CONF_ENTITY_ID,
    CONF_NAME,
    EVENT_HOMEASSISTANT_STOP,
    STATE_OFF,
    Platform,
)
from homeassistant.core import Context
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady, Unauthorized
from homeassistant.helpers import entity_registry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.oref_alert.const import (
    ADD_AREAS,
    ADD_SENSOR_ACTION,
    AREAS_STATUS_ACTION,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_COUNTRY_UPDATES,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    CONF_SENSORS,
    DOMAIN,
    EDIT_SENSOR_ACTION,
    LAST_UPDATE_ACTION,
    MANUAL_EVENT_END_ACTION,
    MANUAL_EVENT_END_TITLE,
    OREF_ALERT_UNIQUE_ID,
    REMOVE_AREAS,
    REMOVE_SENSOR_ACTION,
    SYNTHETIC_ALERT_ACTION,
    PublishedData,
)
from custom_components.oref_alert.coordinator import OrefAlertDataUpdateCoordinator
from custom_components.oref_alert.metadata.area_info import AREA_INFO

from .utils import mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

DEFAULT_OPTIONS: dict[str, list[str]] = {CONF_AREAS: []}
ENTITY_ID = f"{Platform.BINARY_SENSOR}.{OREF_ALERT_UNIQUE_ID}"


async def test_setup(hass: HomeAssistant, entity_registry: er.EntityRegistry) -> None:
    """Test basic setup flow."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    entity = entity_registry.async_get(ENTITY_ID)
    assert entity is not None
    assert entity.device_id is not None
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not hass.states.get(ENTITY_ID)


async def test_save_on_homeassistant_stop(hass: HomeAssistant) -> None:
    """Test coordinator state is saved on HA stop event."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hasattr(config_entry, "runtime_data")
    coordinator_async_save = AsyncMock()
    bus_events_async_save = AsyncMock()
    config_entry.runtime_data.coordinator.async_save = coordinator_async_save
    config_entry.runtime_data.bus_events.async_save = bus_events_async_save

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done(wait_background_tasks=True)

    coordinator_async_save.assert_awaited_once()
    bus_events_async_save.assert_awaited_once()


async def test_config_update(hass: HomeAssistant) -> None:
    """Test config update flow."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    attributes = state.attributes
    assert attributes is not None
    assert attributes[CONF_AREAS] == []
    hass.config_entries.async_update_entry(
        config_entry, options={**DEFAULT_OPTIONS, CONF_AREAS: ["פתח תקווה"]}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    attributes = state.attributes
    assert attributes is not None
    assert attributes[CONF_AREAS] == ["פתח תקווה"]
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.allowed_logs(
    [
        "Error fetching oref_alert data: refresh failed",
        "Error loading oref_alert config entry. Will retry later.",
    ]
)
async def test_config_retry(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config retry on setup failure."""
    monkeypatch.setattr(
        OrefAlertDataUpdateCoordinator,
        "_async_update_data",
        AsyncMock(side_effect=UpdateFailed("refresh failed")),
    )
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert "Error loading oref_alert config entry. Will retry later." in caplog.text
    assert (
        "Config entry 'Mock Title' for oref_alert integration not ready yet"
        in caplog.text
    )

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_add_remove_sensor_action(hass: HomeAssistant) -> None:
    """Test add_sensor and remove_sensor custom actions."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.services.async_call(
        DOMAIN, ADD_SENSOR_ACTION, {CONF_NAME: "test", CONF_AREAS: []}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = f"{ENTITY_ID}_test"
    assert hass.states.get(entity_id) is not None
    entity_reg = entity_registry.async_get(hass)
    entity = entity_reg.async_get(entity_id)
    assert entity is not None
    config_id = entity.config_entry_id
    assert config_id is not None
    entity_config_entry = hass.config_entries.async_get_entry(config_id)
    assert entity_config_entry is not None
    assert "test" in entity_config_entry.options[CONF_SENSORS]

    await hass.services.async_call(
        DOMAIN,
        REMOVE_SENSOR_ACTION,
        {CONF_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity_id) is None
    assert entity_reg.async_get(entity_id) is None
    entity_config_entry = hass.config_entries.async_get_entry(config_id)
    assert entity_config_entry is not None
    assert "test" not in entity_config_entry.options[CONF_SENSORS]


async def test_edit_sensor_actions(hass: HomeAssistant) -> None:
    """Test edit_sensor custom action."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    await hass.services.async_call(
        DOMAIN,
        ADD_SENSOR_ACTION,
        {CONF_NAME: "test", CONF_AREAS: ["פתח תקווה"]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = f"{ENTITY_ID}_test"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[CONF_AREAS] == ["פתח תקווה"]

    response = await hass.services.async_call(
        DOMAIN,
        EDIT_SENSOR_ACTION,
        {
            CONF_ENTITY_ID: entity_id,
            ADD_AREAS: ["גבעת שמואל"],
            REMOVE_AREAS: ["פתח תקווה"],
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert response == {CONF_AREAS: ["גבעת שמואל"]}
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[CONF_AREAS] == ["גבעת שמואל"]

    response = await hass.services.async_call(
        DOMAIN,
        EDIT_SENSOR_ACTION,
        {
            CONF_ENTITY_ID: entity_id,
            ADD_AREAS: ["פתח תקווה"],
        },
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert response is None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[CONF_AREAS] == ["גבעת שמואל", "פתח תקווה"]


async def test_areas_status_action(hass: HomeAssistant) -> None:
    """Test areas_status custom action."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    areas = ["קריית שמונה", "תל אביב - דרום העיר ויפו"]
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: areas, CONF_DURATION: 20},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    await hass.services.async_call(
        DOMAIN,
        MANUAL_EVENT_END_ACTION,
        {CONF_AREA: [areas[0]]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    response = await hass.services.async_call(
        DOMAIN,
        AREAS_STATUS_ACTION,
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert response
    assert list(response) == [areas[1]]
    area_response: PublishedData = response[areas[1]]  # pyright: ignore[reportAssignmentType]
    assert area_response
    assert area_response["area"] == areas[1]
    assert area_response["category"] == 1
    assert area_response["channel"] == "synthetic"
    assert isinstance(area_response["home_distance"], float)
    assert isinstance(area_response["latitude"], float)
    assert isinstance(area_response["longitude"], float)
    assert isinstance(area_response["icon"], str)
    assert isinstance(area_response["emoji"], str)
    assert isinstance(area_response["district"], str)
    assert area_response["title"] == "התרעה סינטטית לצורכי בדיקות"
    assert area_response["type"] == "alert"
    assert dt_util.parse_datetime(area_response[ATTR_DATE]) is not None


async def test_areas_status_action_non_admin(hass: HomeAssistant) -> None:
    """Test areas_status custom action can be called by non-admin users."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    await hass.auth.async_create_user("owner")
    non_admin_user = await hass.auth.async_create_user("non_admin")
    context = Context(user_id=non_admin_user.id)

    response = await hass.services.async_call(
        DOMAIN,
        AREAS_STATUS_ACTION,
        blocking=True,
        context=context,
        return_response=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert response == {}

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            SYNTHETIC_ALERT_ACTION,
            {CONF_AREA: ["קריית שמונה"], CONF_DURATION: 20},
            blocking=True,
            context=context,
        )


async def test_last_update_action(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test last_update custom action."""
    freezer.move_to("2026-01-01 00:00:00+00:00")
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    initial = await hass.services.async_call(
        DOMAIN,
        LAST_UPDATE_ACTION,
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert initial == {"last_update": None, "version": "1767225600"}

    areas = ["קריית שמונה", "תל אביב - דרום העיר ויפו"]
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: areas, CONF_DURATION: 20},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    response = await hass.services.async_call(
        DOMAIN,
        LAST_UPDATE_ACTION,
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert response
    assert dt_util.parse_datetime(response["last_update"]) is not None  # pyright: ignore[reportArgumentType]
    assert response["version"] == "1767225600"


async def test_last_update_action_non_admin(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test last_update custom action can be called by non-admin users."""
    freezer.move_to("2026-01-01 00:00:00+00:00")
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    non_admin_user = await hass.auth.async_create_user("non_admin_map")
    context = Context(user_id=non_admin_user.id)

    response = await hass.services.async_call(
        DOMAIN,
        LAST_UPDATE_ACTION,
        blocking=True,
        context=context,
        return_response=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert response == {"last_update": None, "version": "1767225600"}


@pytest.mark.slow
async def test_areas_status_action_all_areas_alias(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test areas_status returns area-specific data for all-areas alerts."""
    freezer.move_to("2025-06-13 03:00:00+03:00")
    mock_urls(aioclient_mock, None, "single_all_areas_alert_history.json")

    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    response = await hass.services.async_call(
        DOMAIN,
        AREAS_STATUS_ACTION,
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert isinstance(response, dict)
    assert "קריית שמונה" in response
    data: PublishedData = response["קריית שמונה"]  # pyright: ignore[reportAssignmentType]
    assert data["area"] == "קריית שמונה"
    assert data["district"] == "קו העימות"
    assert data["latitude"] == AREA_INFO["קריית שמונה"]["lat"]
    assert data["longitude"] == AREA_INFO["קריית שמונה"]["lon"]


@pytest.mark.parametrize(
    "areas",
    [
        "קריית שמונה",
        ["קריית שמונה", "תל אביב - דרום העיר ויפו"],
    ],
    ids=("str", "list"),
)
async def test_synthetic_alert_action(hass: HomeAssistant, areas: str | list) -> None:
    """Test synthetic_alert custom action."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: areas, CONF_DURATION: 20},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert (
        len(state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS]) == 1
        if isinstance(areas, str)
        else len(areas)
    )
    for index, area in enumerate([areas] if isinstance(areas, str) else areas):
        assert state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS][index]["data"] == area


async def test_manual_event_end_action(hass: HomeAssistant) -> None:
    """Test manual_event_end custom action."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    areas = ["קריית שמונה", "תל אביב - דרום העיר ויפו"]
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: areas, CONF_DURATION: 20},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    await hass.services.async_call(
        DOMAIN,
        MANUAL_EVENT_END_ACTION,
        {},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert len(state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS]) == 0
    assert len(state.attributes[ATTR_COUNTRY_UPDATES]) == len(areas)
    for record in state.attributes[ATTR_COUNTRY_UPDATES]:
        assert record["title"] == MANUAL_EVENT_END_TITLE


async def test_manual_event_end_action_filtered_areas(hass: HomeAssistant) -> None:
    """Test manual_event_end custom action with selected areas."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    areas = ["קריית שמונה", "תל אביב - דרום העיר ויפו"]
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: areas, CONF_DURATION: 20},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    await hass.services.async_call(
        DOMAIN,
        MANUAL_EVENT_END_ACTION,
        {CONF_AREA: [areas[0]]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert len(state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS]) == 1
    assert state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS][0]["data"] == areas[1]
    assert len(state.attributes[ATTR_COUNTRY_UPDATES]) == 1
    assert state.attributes[ATTR_COUNTRY_UPDATES][0]["data"] == areas[0]
    assert state.attributes[ATTR_COUNTRY_UPDATES][0]["title"] == MANUAL_EVENT_END_TITLE


async def test_sensor_name_migration(hass: HomeAssistant) -> None:
    """Test sensor name migration."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_AREAS: [],
            CONF_SENSORS: {"Oref Alert Test": []},
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "Test" in config_entry.options[CONF_SENSORS]


async def test_unknown_area(hass: HomeAssistant) -> None:
    """Test repair ticket of an unknown area."""
    repairs = []
    unregister = hass.bus.async_listen(
        ir.EVENT_REPAIRS_ISSUE_REGISTRY_UPDATED,
        lambda event, repairs=repairs: repairs.append(event),
    )
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_AREAS: ["unknown1"],
            CONF_SENSORS: {"x": ["unknown2"]},
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(repairs) == 2
    for i in range(2):
        assert repairs[i].data["action"] == "create"
        assert repairs[i].data["domain"] == DOMAIN
    assert {repair.data["issue_id"] for repair in repairs} == {
        f"{DOMAIN}_unknown1",
        f"{DOMAIN}_unknown2",
    }
    unregister()


async def test_action_without_config_entry(hass: HomeAssistant) -> None:
    """Test action service without config entry."""
    for service in [
        ADD_SENSOR_ACTION,
        REMOVE_SENSOR_ACTION,
        EDIT_SENSOR_ACTION,
        AREAS_STATUS_ACTION,
        SYNTHETIC_ALERT_ACTION,
        MANUAL_EVENT_END_ACTION,
    ]:
        assert not hass.services.has_service(DOMAIN, service)

    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)

    async def call() -> None:
        await hass.services.async_call(
            DOMAIN,
            AREAS_STATUS_ACTION,
            blocking=True,
            return_response=True,
        )

    await call()

    assert await hass.config_entries.async_set_disabled_by(
        config_entry.entry_id, ConfigEntryDisabler.USER
    )

    with pytest.raises(ConfigEntryNotReady) as exc:
        await call()
    assert str(exc.value) == "Config entry not loaded"

    assert await hass.config_entries.async_remove(config_entry.entry_id)

    with pytest.raises(ConfigEntryError) as exc:
        await call()
    assert str(exc.value) == "Config entry not found"
