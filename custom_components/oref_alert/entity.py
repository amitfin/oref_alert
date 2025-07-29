"""Support for representing oref alert entity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TITLE
from .coordinator import OrefAlertDataUpdateCoordinator

if TYPE_CHECKING:
    from . import OrefAlertConfigEntry


class OrefAlertEntity(Entity):
    """Base class for oref alert entities."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, config_entry: OrefAlertConfigEntry) -> None:
        """Initialize the entity."""
        self._config_entry = config_entry
        self._attr_device_info = DeviceInfo(
            name=TITLE,
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, config_entry.entry_id)},
        )

    @staticmethod
    def calculate_name(name: str, suffix: str | None = None) -> str:
        """Calculate the entity name."""
        name = name.removeprefix(TITLE).strip()
        if not suffix:
            return name
        if not name:
            return suffix
        return f"{name} {suffix}"


class OrefAlertCoordinatorEntity(
    OrefAlertEntity, CoordinatorEntity[OrefAlertDataUpdateCoordinator]
):
    """Base class for entities that use a coordinator."""

    def __init__(self, config_entry: OrefAlertConfigEntry) -> None:
        """Initialize the entity with a coordinator."""
        OrefAlertEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, config_entry.runtime_data.coordinator)  # type: ignore  # noqa: PGH003
