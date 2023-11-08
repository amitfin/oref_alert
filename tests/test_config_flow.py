"""The tests for the config_flow file."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert.const import (
    DOMAIN,
    TITLE,
    CONF_AREAS,
    CONF_ALERT_MAX_AGE,
    CONF_OFF_ICON,
    CONF_ON_ICON,
    CONF_POLL_INTERVAL,
    CONF_SENSORS,
    DEFAULT_ALERT_MAX_AGE,
    DEFAULT_ON_ICON,
    DEFAULT_OFF_ICON,
    DEFAULT_POLL_INTERVAL,
)

DEFAULT_OPTIONS = {
    CONF_AREAS: [],
    CONF_ALERT_MAX_AGE: DEFAULT_ALERT_MAX_AGE,
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
    CONF_ON_ICON: DEFAULT_ON_ICON,
    CONF_OFF_ICON: DEFAULT_OFF_ICON,
}
DEFAULT_SENSORS = {"dummy": ["dummy"]}


async def test_config_flow_defaults(hass: HomeAssistant) -> None:
    """Test the user flow with default values."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == SOURCE_USER
    assert "flow_id" in result

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_AREAS: []},
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == TITLE
    assert result2["options"] == DEFAULT_OPTIONS


async def test_second_config_flow(hass: HomeAssistant) -> None:
    """Test a try to add a second instance."""
    MockConfigEntry(domain=DOMAIN, title=TITLE, options=DEFAULT_OPTIONS).add_to_hass(
        hass
    )

    # Should fail, same DOMAIN
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_area_auto_detect(hass: HomeAssistant) -> None:
    """Test area auto detect flow."""
    hass.config.latitude = 32.072
    hass.config.longitude = 34.879

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"] == {"area": "פתח תקווה"}
    assert "flow_id" in result

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == TITLE
    assert result2["options"] == {**DEFAULT_OPTIONS, **{CONF_AREAS: ["פתח תקווה"]}}


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test the options flow."""
    options = {**DEFAULT_OPTIONS, **{CONF_SENSORS: DEFAULT_SENSORS}}
    config_entry = MockConfigEntry(domain=DOMAIN, title=TITLE, options=options)
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={**DEFAULT_OPTIONS, **{CONF_ALERT_MAX_AGE: 15}},
    )
    assert result2.get("type") == FlowResultType.CREATE_ENTRY
    options[CONF_ALERT_MAX_AGE] = 15
    assert result2.get("data") == options
