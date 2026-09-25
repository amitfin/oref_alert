"""Shared helpers for the Oref Alert integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.util import slugify

from .const import (
    ALL_AREAS_ID_SUFFIX,
    DOMAIN,
    LEGACY_END_TIME_ID_SUFFIX,
    LEGACY_PREEMPTIVE_UPDATE_ID_SUFFIX,
    LEGACY_STATUS_ID_SUFFIX,
    OREF_ALERT_UNIQUE_ID,
    TIME_TO_SHELTER_ID_SUFFIX,
    AreaStatus,
    RecordType,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import OrefAlertConfigEntry
    from .const import RecordAndMetadata


def custom_sensor_unique_id(name: str, suffix: str | None = None) -> str:
    """Return the unique ID of a custom sensor's entity (or companion by suffix)."""
    return slugify(
        f"{OREF_ALERT_UNIQUE_ID}_{name.lower().replace(' ', '_')}"
        + (f"_{suffix}" if suffix else "")
    )


def sensor_unique_ids(name: str) -> set[tuple[str, str]]:
    """
    Return (domain, unique_id) of every entity a sensor may have.

    Includes entities which are created conditionally or were used by older
    versions. An empty name is the default sensor.
    """
    unique_id = custom_sensor_unique_id(name)
    return {
        (Platform.BINARY_SENSOR, unique_id),
        (Platform.EVENT, unique_id),
        (Platform.SENSOR, unique_id),
        (Platform.SENSOR, custom_sensor_unique_id(name, TIME_TO_SHELTER_ID_SUFFIX)),
        (Platform.SENSOR, custom_sensor_unique_id(name, LEGACY_END_TIME_ID_SUFFIX)),
        (Platform.SENSOR, custom_sensor_unique_id(name, LEGACY_STATUS_ID_SUFFIX)),
        (
            Platform.BINARY_SENSOR,
            custom_sensor_unique_id(name, LEGACY_PREEMPTIVE_UPDATE_ID_SUFFIX),
        ),
    }


BUILT_IN_SENSORS_UNIQUE_IDS: Final = sensor_unique_ids("") | {
    (Platform.BINARY_SENSOR, f"{OREF_ALERT_UNIQUE_ID}_{ALL_AREAS_ID_SUFFIX}"),
}


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
