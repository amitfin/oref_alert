"""The tests for the binary_sensor file."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON, Platform
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    ADD_SENSOR_ACTION,
    ALL_AREAS_ID_SUFFIX,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_COUNTRY_ALERTS,
    ATTR_COUNTRY_UPDATES,
    ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
    ATTR_SELECTED_AREAS_ALERTS,
    ATTR_SELECTED_AREAS_UPDATES,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALL_ALERTS_ATTRIBUTES,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    CONF_OFF_ICON,
    CONF_ON_ICON,
    CONF_POLL_INTERVAL,
    DOMAIN,
    OREF_ALERT_UNIQUE_ID,
    SYNTHETIC_ALERT_ACTION,
)

from .utils import load_json_fixture, mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

DEFAULT_OPTIONS = {
    CONF_AREAS: ["בארי"],
    CONF_ALERT_ACTIVE_DURATION: 10,
    CONF_ALL_ALERTS_ATTRIBUTES: True,
}
ENTITY_ID = f"{Platform.BINARY_SENSOR}.{OREF_ALERT_UNIQUE_ID}"


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


async def test_state(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test entity state."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")

    config_id = await async_setup(hass)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON

    freezer.move_to("2023-10-07 06:39:50+03:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON

    freezer.move_to("2023-10-07 06:40:01+03:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF

    await async_shutdown(hass, config_id)


@pytest.mark.parametrize(
    "areas",
    ["תל אביב - כל האזורים", "מחוז דן"],
    ids=("City all areas", "District"),
)
async def test_real_time_alert_area_expansion(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, areas: str
) -> None:
    """Test real time alert and city expansion."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(hass, {CONF_AREAS: [areas]})
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON
    await async_shutdown(hass, config_id)


async def test_state_attributes(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test state attributes."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "multi_alerts_real_time.json", "multi_alerts_history.json"
    )
    config_id = await async_setup(hass)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    active_area_alert = load_json_fixture(
        "single_alert_history.json", "website-history"
    )
    assert state.attributes[CONF_ALERT_ACTIVE_DURATION] == 10
    assert state.attributes[ATTR_SELECTED_AREAS_ACTIVE_ALERTS] == active_area_alert
    assert state.attributes[ATTR_SELECTED_AREAS_ALERTS] == active_area_alert
    combined_alerts = load_json_fixture("combined_alerts.json")
    assert state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS] == combined_alerts
    assert state.attributes[ATTR_COUNTRY_ALERTS] == combined_alerts
    await async_shutdown(hass, config_id)


async def test_interval(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test setting the interval."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(
        hass,
        {
            CONF_AREAS: ["תל אביב - כל האזורים"],
        },
    )

    # Test the "update" path which is more involved than initial configuration.
    config_entry = hass.config_entries.async_get_entry(config_id)
    assert config_entry is not None
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.options,
            CONF_POLL_INTERVAL: 125,
            CONF_ALERT_ACTIVE_DURATION: 1,
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON
    mock_urls(aioclient_mock, None, None)

    freezer.tick(datetime.timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON

    freezer.tick(datetime.timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF

    await async_shutdown(hass, config_id)


async def test_state_on_caching(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that state 'on' is cached properly."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(
        hass,
        {
            CONF_AREAS: ["תל אביב - כל האזורים"],
        },
    )

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON
    mock_urls(aioclient_mock, None, None)

    freezer.tick(datetime.timedelta(seconds=595))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON

    freezer.tick(datetime.timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF

    await async_shutdown(hass, config_id)


async def test_state_no_caching_for_synthetic(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that state 'on' is not cached for synthetic alerts."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: DEFAULT_OPTIONS[CONF_AREAS][0], CONF_DURATION: 20},
        blocking=True,
    )

    freezer.tick(datetime.timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON

    freezer.tick(datetime.timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF

    await async_shutdown(hass, config_id)


async def test_icons(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test state attributes."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(
        hass,
        {
            CONF_AREAS: ["תל אביב - כל האזורים"],
            CONF_ON_ICON: "mdi:emoticon-sad",
            CONF_OFF_ICON: "mdi:emoticon-happy",
        },
    )
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["icon"] == "mdi:emoticon-sad"
    mock_urls(aioclient_mock, None, None)
    freezer.tick(datetime.timedelta(seconds=600))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["icon"] == "mdi:emoticon-happy"
    await async_shutdown(hass, config_id)


async def test_unrecognized_area(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test unrecognized area."""
    mock_urls(aioclient_mock, "unrecognized_alert.json", None)
    config_id = await async_setup(hass)
    assert caplog.text.count("Alert has an unrecognized area: שכם") == 1
    freezer.tick(datetime.timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert caplog.text.count("Alert has an unrecognized area: שכם") == 1
    await async_shutdown(hass, config_id)
    assert "Alert has an unrecognized area: סעד" not in caplog.text


async def test_additional_sensor(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test state of an additional sensor."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(hass)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    await hass.services.async_call(
        DOMAIN,
        ADD_SENSOR_ACTION,
        {CONF_NAME: "test", CONF_AREAS: ["תל אביב - כל האזורים"]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(f"{ENTITY_ID}_test")
    assert state is not None
    assert state.state == STATE_ON
    await async_shutdown(hass, config_id)


async def test_all_areas_sensor(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test all-areas sensor."""
    freezer.move_to("2023-10-10 11:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_random_area_history.json")
    config_id = await async_setup(hass)
    state = hass.states.get(f"{ENTITY_ID}_{ALL_AREAS_ID_SUFFIX}")
    assert state is not None
    assert state.state == STATE_ON
    expected_alerts = load_json_fixture(
        "single_alert_random_area_history.json", "website-history"
    )
    assert state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS] == expected_alerts
    assert state.attributes[ATTR_COUNTRY_ALERTS] == expected_alerts
    await async_shutdown(hass, config_id)


@pytest.mark.parametrize(
    ("real_time_file", "history_file", "test_expired"),
    [
        (None, "single_update_history.json", True),
        ("single_update_real_time.json", None, False),
    ],
    ids=["website-history", "real_time"],
)
async def test_updates_attribute(  # noqa: PLR0913
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    real_time_file: str | None,
    history_file: str | None,
    test_expired: bool,  # noqa: FBT001
) -> None:
    """Test updates attribute."""
    freezer.move_to("2025-04-26 03:30:00+03:00")
    mock_urls(aioclient_mock, real_time_file, history_file)
    alerts = load_json_fixture(
        "single_update_history.json", "website-history" if history_file else "website"
    )
    if real_time_file:
        alerts[0]["category"] = 13

    config_id = await async_setup(hass, {CONF_AREAS: ["פתח תקווה"]})
    await hass.services.async_call(
        DOMAIN,
        ADD_SENSOR_ACTION,
        {CONF_NAME: "test", CONF_AREAS: ["פתח תקווה"]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    entities = (
        (
            f"{ENTITY_ID}_test",
            ATTR_SELECTED_AREAS_UPDATES,
        ),
        (
            f"{ENTITY_ID}_test",
            ATTR_COUNTRY_UPDATES,
        ),
        (
            f"{ENTITY_ID}_{ALL_AREAS_ID_SUFFIX}",
            ATTR_COUNTRY_UPDATES,
        ),
    )

    for entity_id, attribute in entities:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_OFF
        assert state.attributes[attribute] == alerts

    if test_expired:
        freezer.move_to("2025-04-26 03:40:01+03:00")
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)

        for entity_id, attribute in entities:
            state = hass.states.get(entity_id)
            assert state is not None
            assert state.state == STATE_OFF
            assert not state.attributes[attribute]

    await async_shutdown(hass, config_id)


@pytest.mark.parametrize(
    ("real_time_file", "history_file", "alias"),
    [
        (None, "single_all_areas_alert_history.json", "כל הארץ"),
        ("single_all_areas_alert_real_time.json", None, "ברחבי הארץ"),
    ],
    ids=["website-history", "real_time"],
)
async def test_all_areas_alert(  # noqa: PLR0913
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    real_time_file: str | None,
    history_file: str | None,
    alias: str,
) -> None:
    """Test all areas alert."""
    freezer.move_to("2025-06-13 03:00:00+03:00")
    mock_urls(aioclient_mock, real_time_file, history_file)
    alerts = load_json_fixture(
        "single_all_areas_alert_history.json",
        "website-history" if history_file else "website",
    )
    alerts[0]["data"] = alias

    config_id = await async_setup(hass, {CONF_AREAS: ["פתח תקווה"]})
    await hass.async_block_till_done(wait_background_tasks=True)

    entities = (
        (
            ENTITY_ID,
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
        ),
        (
            f"{ENTITY_ID}_{ALL_AREAS_ID_SUFFIX}",
            ATTR_COUNTRY_ACTIVE_ALERTS,
        ),
    )

    for entity_id, attribute in entities:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_ON
        assert state.attributes[attribute] == alerts, state.attributes[attribute]

    await async_shutdown(hass, config_id)


async def test_all_alerts_attributes_is_off(hass: HomeAssistant) -> None:
    """Test that all alerts attributes are not included when the option is off."""
    config_id = await async_setup(
        hass,
        {
            CONF_AREAS: ["פתח תקווה"],
            CONF_ALL_ALERTS_ATTRIBUTES: False,
        },
    )
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert ATTR_SELECTED_AREAS_ALERTS not in state.attributes
    assert ATTR_COUNTRY_ALERTS not in state.attributes

    state = hass.states.get(f"{ENTITY_ID}_{ALL_AREAS_ID_SUFFIX}")
    assert state is not None
    assert ATTR_COUNTRY_ALERTS not in state.attributes

    await async_shutdown(hass, config_id)
