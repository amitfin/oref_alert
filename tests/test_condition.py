"""The tests for the condition platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import voluptuous as vol
from homeassistant.helpers import condition as condition_helper
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert.const import (
    CONF_AREA,
    CONF_AREAS,
    DOMAIN,
    MANUAL_EVENT_END_ACTION,
)

from .utils import fire_synthetic_alert, mock_urls

if TYPE_CHECKING:
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


async def _async_check(hass: HomeAssistant, condition: dict[str, Any]) -> bool | None:
    """Validate and evaluate a condition config directly, returning its result."""
    config = await condition_helper.async_validate_condition_config(hass, condition)
    checker = await condition_helper.async_from_config(hass, config)
    try:
        return checker.async_check()
    finally:
        checker.async_unload()


# --- oref_alert.home ---


async def test_home_condition_default_state_is_alert_only(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home condition's default state filter excludes pre_alert."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    await fire_synthetic_alert(hass, "בארי", category=14)

    assert await _async_check(hass, {"condition": "oref_alert.home"}) is False

    await async_shutdown(hass, config_id)


async def test_home_condition_matching_alert(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home condition passes for the areas configured on the integration."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    await fire_synthetic_alert(hass, "בארי")

    assert await _async_check(hass, {"condition": "oref_alert.home"}) is True

    await async_shutdown(hass, config_id)


async def test_home_condition_explicit_state(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home condition passes for an explicitly configured state."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    await fire_synthetic_alert(hass, "בארי", category=14)

    condition = {"condition": "oref_alert.home", "state": "pre_alert"}
    assert await _async_check(hass, condition) is True

    await async_shutdown(hass, config_id)


async def test_home_condition_ok_when_no_alert(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home condition passes for state ok when nothing is alerted."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    condition = {"condition": "oref_alert.home", "state": "ok"}
    assert await _async_check(hass, condition) is True

    await async_shutdown(hass, config_id)


async def test_home_condition_ends_back_to_ok(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home condition treats an ended record as ok again."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)
    condition = {"condition": "oref_alert.home", "state": "ok"}

    await fire_synthetic_alert(hass, "בארי")
    assert await _async_check(hass, condition) is False

    await hass.services.async_call(
        DOMAIN, MANUAL_EVENT_END_ACTION, {CONF_AREA: ["בארי"]}, blocking=True
    )
    await hass.async_block_till_done()

    assert await _async_check(hass, condition) is True

    await async_shutdown(hass, config_id)


async def test_home_condition_ignores_non_configured_area(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the home condition only checks the integration's configured areas."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    await fire_synthetic_alert(hass, "תל אביב - מרכז העיר")

    assert await _async_check(hass, {"condition": "oref_alert.home"}) is False

    await async_shutdown(hass, config_id)


async def test_home_condition_without_integration(hass: HomeAssistant) -> None:
    """Test the home condition never passes with no integration configured."""
    assert await _async_check(hass, {"condition": "oref_alert.home"}) is False


async def test_home_condition_fails_closed_for_ok_when_entry_not_loaded(
    hass: HomeAssistant,
) -> None:
    """
    Test state: ok does not trivially pass when the entry exists but isn't loaded.

    Distinct from a config entry that's entirely absent: this exercises the
    "added but never set up" case (state=NOT_LOADED), which the condition's
    loaded-entry check must treat as unavailable.
    """
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    # Deliberately not calling hass.config_entries.async_setup(...).

    condition = {"condition": "oref_alert.home", "state": "ok"}
    assert await _async_check(hass, condition) is False


# --- oref_alert.area ---


async def test_area_condition_matching_explicit_area(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the area condition passes for a matching explicit area."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    await fire_synthetic_alert(hass, "בארי")

    condition = {"condition": "oref_alert.area", "areas": "בארי"}
    assert await _async_check(hass, condition) is True

    await async_shutdown(hass, config_id)


async def test_area_condition_non_matching_explicit_area(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the area condition does not pass for a non-matching explicit area."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    await fire_synthetic_alert(hass, "תל אביב - מרכז העיר")

    condition = {"condition": "oref_alert.area", "areas": "בארי"}
    assert await _async_check(hass, condition) is False

    await async_shutdown(hass, config_id)


async def test_area_condition_rejects_all_areas_alias(hass: HomeAssistant) -> None:
    """Test the schema rejects the all-areas aliases."""
    with pytest.raises(vol.Invalid):
        await condition_helper.async_validate_condition_config(
            hass, {"condition": "oref_alert.area", "areas": "כל הארץ"}
        )


async def test_area_condition_any_area_alert_when_omitted(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the area condition matches any alerted area when areas is omitted."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    # Not one of the integration's configured areas, proving there's no fallback to it.
    await fire_synthetic_alert(hass, "תל אביב - מרכז העיר")

    assert await _async_check(hass, {"condition": "oref_alert.area"}) is True

    await async_shutdown(hass, config_id)


async def test_area_condition_any_area_ok_with_no_alerts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the any-area ok check passes when nothing is alerted anywhere."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    condition = {"condition": "oref_alert.area", "state": "ok"}
    assert await _async_check(hass, condition) is True

    await async_shutdown(hass, config_id)


async def test_area_condition_any_area_ok_survives_one_active_alert(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the any-area ok check still passes when only one area is alerted."""
    mock_urls(aioclient_mock, None, None)
    config_id = await async_setup(hass)

    await fire_synthetic_alert(hass, "בארי")

    condition = {"condition": "oref_alert.area", "state": "ok"}
    assert await _async_check(hass, condition) is True

    await async_shutdown(hass, config_id)


async def test_area_condition_without_integration_explicit_areas(
    hass: HomeAssistant,
) -> None:
    """Test an explicit-areas condition never passes with no integration."""
    condition = {"condition": "oref_alert.area", "areas": "בארי"}
    assert await _async_check(hass, condition) is False


async def test_area_condition_without_integration_any_area_ok(
    hass: HomeAssistant,
) -> None:
    """Test state: ok does not trivially pass with no integration configured."""
    condition = {"condition": "oref_alert.area", "state": "ok"}
    assert await _async_check(hass, condition) is False


async def test_area_condition_without_integration_explicit_areas_ok(
    hass: HomeAssistant,
) -> None:
    """
    Test explicit areas + state: ok does not trivially pass without integration.

    Unlike the omitted-areas case, an explicit area list doesn't route through
    the canonical/active-area branching, so the loaded-entry check is the only
    thing preventing a false pass here.
    """
    condition = {"condition": "oref_alert.area", "areas": "בארי", "state": "ok"}
    assert await _async_check(hass, condition) is False


async def test_area_condition_without_integration_any_area_alert(
    hass: HomeAssistant,
) -> None:
    """Test the any-area alert check never passes with no integration configured."""
    assert await _async_check(hass, {"condition": "oref_alert.area"}) is False
