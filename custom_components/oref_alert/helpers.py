"""Shared helpers for the Oref Alert integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_LOCATION
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .area_utils import AREAS_AND_GROUPS_WITHOUT_ALL_AREAS, expand_areas_and_groups
from .const import ATTR_DISTANCE, ATTR_TYPE, CONF_AREAS, DOMAIN, RecordType

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import OrefAlertConfigEntry

DEFAULT_DISTANCE: Final = 5
DEFAULT_LOCATION: Final = "zone.home"
LOCATION_DOMAINS: Final = ["zone", "device_tracker", "person"]

TYPE_OPTION_SCHEMA: Final[dict[vol.Marker, Any]] = {
    vol.Optional(ATTR_TYPE, default=RecordType.ALERT): vol.All(
        cv.ensure_list, [vol.Coerce(RecordType)]
    ),
}

AREA_TRIGGER_OPTIONS_SCHEMA_DICT: Final[dict[vol.Marker, Any]] = {
    **TYPE_OPTION_SCHEMA,
    vol.Optional(CONF_AREAS): vol.All(
        cv.ensure_list, [vol.In(AREAS_AND_GROUPS_WITHOUT_ALL_AREAS)]
    ),
}

DISTANCE_TRIGGER_OPTIONS_SCHEMA_DICT: Final[dict[vol.Marker, Any]] = {
    **TYPE_OPTION_SCHEMA,
    vol.Required(ATTR_DISTANCE, default=DEFAULT_DISTANCE): cv.positive_float,
    vol.Required(CONF_LOCATION, default=DEFAULT_LOCATION): cv.entity_domain(
        LOCATION_DOMAINS
    ),
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


def home_areas(hass: HomeAssistant) -> list[str]:
    """Return the areas configured on the integration, expanded."""
    if (config_entry := find_config_entry(hass)) is None:
        return []
    return expand_areas_and_groups(config_entry.options[CONF_AREAS])
