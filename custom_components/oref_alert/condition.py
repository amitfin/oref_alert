"""Condition platforms for oref_alert."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast, override

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_OPTIONS
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.automation import move_top_level_schema_fields_to_options
from homeassistant.helpers.condition import Condition, ConditionConfig

from .area_utils import AREAS_AND_GROUPS_WITHOUT_ALL_AREAS, expand_areas_and_groups
from .const import ATTR_STATE, CONF_AREAS, AreaStatus
from .helpers import find_config_entry, record_status
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Unpack

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.condition import ConditionCheckParams
    from homeassistant.helpers.typing import ConfigType

    from . import OrefAlertConfigEntry

STATE_OPTION_SCHEMA: Final[dict[vol.Marker, Any]] = {
    vol.Optional(ATTR_STATE, default=AreaStatus.ALERT): vol.All(
        cv.ensure_list, [vol.Coerce(AreaStatus)]
    ),
}

AREA_CONDITION_OPTIONS_SCHEMA_DICT: Final[dict[vol.Marker, Any]] = {
    **STATE_OPTION_SCHEMA,
    vol.Optional(CONF_AREAS): vol.All(
        cv.ensure_list, [vol.In(AREAS_AND_GROUPS_WITHOUT_ALL_AREAS)]
    ),
}


def _loaded_config_entry(hass: HomeAssistant) -> OrefAlertConfigEntry | None:
    """Return the integration's config entry, or None unless it's loaded."""
    config_entry = find_config_entry(hass)
    if config_entry is None or config_entry.state is not ConfigEntryState.LOADED:
        return None
    return config_entry


class _RecordCondition(Condition):
    """Shared base for oref_alert conditions."""

    _options_schema: ClassVar[dict[vol.Marker, Any]]

    @classmethod
    @override
    async def async_validate_complete_config(
        cls, hass: HomeAssistant, complete_config: ConfigType
    ) -> ConfigType:
        """Validate complete config, allowing the flat (non-options) shorthand."""
        complete_config = move_top_level_schema_fields_to_options(
            complete_config, cls._options_schema
        )
        return await super().async_validate_complete_config(hass, complete_config)

    @classmethod
    @override
    async def async_validate_config(
        cls, _: HomeAssistant, config: ConfigType
    ) -> ConfigType:
        """Validate config against the options schema, wrapped in CONF_OPTIONS."""
        schema = vol.Schema({vol.Required(CONF_OPTIONS): cls._options_schema})
        return cast("ConfigType", schema(config))

    def __init__(self, hass: HomeAssistant, config: ConditionConfig) -> None:
        """Initialize condition."""
        super().__init__(hass, config)
        assert config.options is not None  # noqa: S101
        self._states = set(config.options[ATTR_STATE])

    @abc.abstractmethod
    def _areas(self, config_entry: OrefAlertConfigEntry) -> Iterable[str]:
        """Return the candidate areas to check."""

    @override
    def _async_check(self, **kwargs: Unpack[ConditionCheckParams]) -> bool:
        """Test if any candidate area currently matches one of the selected states."""
        if (config_entry := _loaded_config_entry(self._hass)) is None:
            return False
        return any(
            record_status(config_entry.runtime_data.coordinator.data.areas.get(area))
            in self._states
            for area in self._areas(config_entry)
        )


class HomeAlertCondition(_RecordCondition):
    """Passes when the integration's configured areas match a selected state."""

    _options_schema = STATE_OPTION_SCHEMA

    @override
    def _areas(self, config_entry: OrefAlertConfigEntry) -> Iterable[str]:
        """Return the areas configured on the integration."""
        return expand_areas_and_groups(config_entry.options[CONF_AREAS])


class AreaAlertCondition(_RecordCondition):
    """Passes when the selected areas match one of the selected states."""

    _options_schema = AREA_CONDITION_OPTIONS_SCHEMA_DICT

    def __init__(self, hass: HomeAssistant, config: ConditionConfig) -> None:
        """Initialize condition."""
        super().__init__(hass, config)
        assert config.options is not None  # noqa: S101
        areas = config.options.get(CONF_AREAS)
        self._areas_option: list[str] | None = (
            expand_areas_and_groups(areas) if areas is not None else None
        )

    @override
    def _areas(self, config_entry: OrefAlertConfigEntry) -> Iterable[str]:
        """Return the configured areas, or the candidates for "any area"."""
        if self._areas_option is not None:
            return self._areas_option
        if AreaStatus.OK in self._states:
            return AREAS
        return (
            area
            for area, record in config_entry.runtime_data.coordinator.data.areas.items()
            if record_status(record) is not AreaStatus.OK
        )


CONDITIONS: dict[str, type[Condition]] = {
    "home": HomeAlertCondition,
    "area": AreaAlertCondition,
}


async def async_get_conditions(_: HomeAssistant) -> dict[str, type[Condition]]:
    """Return the oref_alert conditions."""
    return CONDITIONS
