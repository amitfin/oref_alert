"""Tests for helper functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert.const import CONF_AREAS, DOMAIN
from custom_components.oref_alert.helpers import get_config_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

DEFAULT_OPTIONS: dict[str, list[str]] = {CONF_AREAS: []}


async def test_get_config_entry_returns_loaded_entry(hass: HomeAssistant) -> None:
    """Test loaded config entry is returned."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert get_config_entry(hass).entry_id == config_entry.entry_id


def test_get_config_entry_raises_when_not_loaded(hass: HomeAssistant) -> None:
    """Test config entry must be loaded."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)

    with pytest.raises(ConfigEntryNotReady) as exc:
        get_config_entry(hass)

    assert str(exc.value) == "config_entry_not_loaded"


def test_get_config_entry_raises_when_missing(hass: HomeAssistant) -> None:
    """Test config entry must exist."""
    with pytest.raises(ConfigEntryError) as exc:
        get_config_entry(hass)

    assert str(exc.value) == "no_config_entry"
