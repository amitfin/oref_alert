"""Trigger platforms for oref_alert."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast, override

import voluptuous as vol
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_LOCATION,
    CONF_OPTIONS,
    UnitOfLength,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.automation import move_top_level_schema_fields_to_options
from homeassistant.helpers.location import has_location
from homeassistant.helpers.trigger import Trigger, TriggerConfig
from homeassistant.util.location import distance as calculate_distance

from .area_utils import AREAS_AND_GROUPS_WITHOUT_ALL_AREAS, expand_areas_and_groups
from .const import (
    ATTR_AREA,
    ATTR_DISTANCE,
    ATTR_RECORDS,
    ATTR_TYPE,
    CONF_AREAS,
    OREF_ALERT_RECORD_EVENT,
    RecordType,
)
from .helpers import find_config_entry

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Mapping

    from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant
    from homeassistant.helpers.trigger import (
        TriggerActionRunner,
        TriggerNotTriggeredReporter,
    )
    from homeassistant.helpers.typing import ConfigType

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


def _home_areas(hass: HomeAssistant) -> list[str]:
    """Return the areas configured on the integration, expanded."""
    if (config_entry := find_config_entry(hass)) is None:
        return []
    return expand_areas_and_groups(config_entry.options[CONF_AREAS])


def _attach_record_batch_listener(
    hass: HomeAssistant,
    matches: Callable[[Mapping[str, Any]], bool],
    run_action: TriggerActionRunner,
) -> CALLBACK_TYPE:
    """
    Listen for oref_alert records, firing once per refresh with all matches.

    bus_events._async_update fires one oref_alert_record event per area,
    synchronously, within a single non-awaited callback whenever the
    coordinator refreshes. Buffering matches and flushing via a task
    coalesces every match from one refresh into a single trigger firing:
    the flush task cannot start until that callback (and everything above
    it) returns control to the event loop, which only happens after every
    event from the current refresh has already been dispatched to (and
    buffered by) this listener. Scheduling it with hass.async_create_task
    (rather than e.g. loop.call_soon) is what lets hass.async_block_till_done
    reliably wait for it, since it's only tracked tasks that block it.
    """
    pending: list[dict[str, Any]] = []
    flush_task: asyncio.Task[None] | None = None

    async def flush() -> None:
        """Fire once with every record buffered since the last flush."""
        nonlocal flush_task
        flush_task = None
        records = pending.copy()
        pending.clear()
        areas = ", ".join(record.get(ATTR_AREA, "") for record in records)
        run_action({ATTR_RECORDS: records}, f"oref_alert records for {areas}")

    @callback
    def handle_event(event: Event) -> None:
        """Buffer a matching record and schedule a flush."""
        nonlocal flush_task
        if not matches(event.data):
            return
        pending.append(dict(event.data))
        if flush_task is None:
            flush_task = hass.async_create_task(flush(), eager_start=False)

    unsub = hass.bus.async_listen(OREF_ALERT_RECORD_EVENT, handle_event)

    @callback
    def unsub_and_cancel_flush() -> None:
        """Unsubscribe and cancel a not-yet-run flush so it can't fire stale."""
        unsub()
        if flush_task is not None:
            flush_task.cancel()

    return unsub_and_cancel_flush


class _RecordTrigger(Trigger):
    """
    Shared base for oref_alert triggers.

    Subclasses plug in their own top-level/options schemas and implement
    `_extra_matches` for their own filtering (areas, distance, ...); this
    base class handles config validation boilerplate, the shared `type`
    filter, and attaching the batching listener.
    """

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

    def __init__(self, hass: HomeAssistant, config: TriggerConfig) -> None:
        """Initialize trigger."""
        super().__init__(hass, config)
        assert config.options is not None  # noqa: S101
        self._types = set(config.options[ATTR_TYPE])

    @abc.abstractmethod
    def _extra_matches(self, data: Mapping[str, Any]) -> bool:
        """Test trigger-specific filtering beyond the shared type check."""

    @override
    async def async_attach_runner(
        self,
        run_action: TriggerActionRunner,
        did_not_trigger: TriggerNotTriggeredReporter | None = None,
    ) -> CALLBACK_TYPE:
        """Listen for oref_alert records matching the configured type and filter."""

        def matches(data: Mapping[str, Any]) -> bool:
            return data.get(ATTR_TYPE) in self._types and self._extra_matches(data)

        return _attach_record_batch_listener(self._hass, matches, run_action)


class HomeAlertTrigger(_RecordTrigger):
    """Fires for oref_alert records matching the areas configured on the integration."""

    _options_schema = TYPE_OPTION_SCHEMA

    @override
    def _extra_matches(self, data: Mapping[str, Any]) -> bool:
        """Test if the record matches the areas configured on the integration."""
        return data.get(ATTR_AREA) in _home_areas(self._hass)


class AreaAlertTrigger(_RecordTrigger):
    """Fires for oref_alert records matching the selected areas and type."""

    _options_schema = AREA_TRIGGER_OPTIONS_SCHEMA_DICT

    def __init__(self, hass: HomeAssistant, config: TriggerConfig) -> None:
        """Initialize trigger."""
        super().__init__(hass, config)
        assert config.options is not None  # noqa: S101
        areas = config.options.get(CONF_AREAS)
        self._areas: list[str] | None = (
            expand_areas_and_groups(areas) if areas is not None else None
        )

    @override
    def _extra_matches(self, data: Mapping[str, Any]) -> bool:
        """Test if the record matches the configured areas."""
        return self._areas is None or data.get(ATTR_AREA) in self._areas


class DistanceAlertTrigger(_RecordTrigger):
    """Fires for oref_alert records within a distance of a location entity."""

    _options_schema = DISTANCE_TRIGGER_OPTIONS_SCHEMA_DICT

    def __init__(self, hass: HomeAssistant, config: TriggerConfig) -> None:
        """Initialize trigger."""
        super().__init__(hass, config)
        assert config.options is not None  # noqa: S101
        self._distance: float = config.options[ATTR_DISTANCE]
        self._location: str = config.options[CONF_LOCATION]

    @override
    def _extra_matches(self, data: Mapping[str, Any]) -> bool:
        """Test if the record is within the configured distance."""
        location_state = self._hass.states.get(self._location)
        if location_state is None or not has_location(location_state):
            return False
        record_lat = data.get(ATTR_LATITUDE)
        record_lon = data.get(ATTR_LONGITUDE)
        if record_lat is None or record_lon is None:
            return False
        meters = calculate_distance(
            location_state.attributes[ATTR_LATITUDE],
            location_state.attributes[ATTR_LONGITUDE],
            record_lat,
            record_lon,
        )
        return meters is not None and (
            self._hass.config.units.length(meters, UnitOfLength.METERS)
            <= self._distance
        )


TRIGGERS: dict[str, type[Trigger]] = {
    "home": HomeAlertTrigger,
    "area": AreaAlertTrigger,
    "distance": DistanceAlertTrigger,
}


async def async_get_triggers(_: HomeAssistant) -> dict[str, type[Trigger]]:
    """Return the oref_alert triggers."""
    return TRIGGERS
