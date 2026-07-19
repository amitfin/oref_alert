"""Shared helpers for the Oref Alert integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import (
    DOMAIN,
    AreaStatus,
    RecordType,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import OrefAlertConfigEntry
    from .const import RecordAndMetadata


def find_config_entry(hass: HomeAssistant) -> OrefAlertConfigEntry | None:
    """Return the integration's config entry, or None when not configured."""
    config_entries = hass.config_entries.async_entries(DOMAIN)
    return config_entries[0] if config_entries else None


def get_config_entry(hass: HomeAssistant) -> OrefAlertConfigEntry:
    """Return the integration's loaded config entry, raising when unavailable."""
    if (config_entry := find_config_entry(hass)) is None:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="no_config_entry",
        )
    if config_entry.state is not ConfigEntryState.LOADED:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_loaded",
        )
    return config_entry


def record_status(record: RecordAndMetadata | None) -> AreaStatus:
    """Return ok/pre_alert/alert for a (possibly absent) area record."""
    record_type = record.record_type if record is not None else None
    if record_type is RecordType.PRE_ALERT or record_type is RecordType.ALERT:
        return AreaStatus(record_type.value)
    return AreaStatus.OK
