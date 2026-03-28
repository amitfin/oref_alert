"""Shared helpers for the Oref Alert integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import OrefAlertConfigEntry


def get_config_entry(hass: HomeAssistant) -> OrefAlertConfigEntry:
    """Get the integration's first (and only) config entry."""
    config_entries = hass.config_entries.async_entries(DOMAIN)
    if not config_entries:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="no_config_entry",
        )
    if config_entries[0].state is not ConfigEntryState.LOADED:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_loaded",
        )
    return config_entries[0]
