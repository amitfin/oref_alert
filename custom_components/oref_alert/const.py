"""Constants for the oref_alert integration."""

from __future__ import annotations

import enum
import logging
import zoneinfo
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from datetime import datetime

DOMAIN: Final = "oref_alert"
TITLE: Final = "Oref Alert"
LOGGER = logging.getLogger(__package__)
IST = zoneinfo.ZoneInfo("Asia/Jerusalem")

ATTR_ALERT: Final = "alert"
ATTR_AREA: Final = "area"
ATTR_COUNTRY_ACTIVE_ALERTS: Final = "country_active_alerts"
ATTR_COUNTRY_UPDATES: Final = "country_updates"
ATTR_DISPLAY: Final = "display"
ATTR_DISTRICT: Final = "district"
ATTR_EMOJI: Final = "emoji"
ATTR_HOME_DISTANCE: Final = "home_distance"
ATTR_RECORD: Final = "record"
ATTR_SELECTED_AREAS_ACTIVE_ALERTS: Final = "selected_areas_active_alerts"
ATTR_SELECTED_AREAS_UPDATES: Final = "selected_areas_updates"
ATTR_TIME_TO_SHELTER: Final = "time_to_shelter"
ATTR_TYPE: Final = "type"

CONF_AREA: Final = "area"
CONF_AREAS: Final = "areas"
CONF_DURATION: Final = "duration"
CONF_SENSORS: Final = "sensors"

ADD_SENSOR_ACTION: Final = "add_sensor"
REMOVE_SENSOR_ACTION: Final = "remove_sensor"
EDIT_SENSOR_ACTION: Final = "edit_sensor"
ADD_AREAS: Final = "add_areas"
REMOVE_AREAS: Final = "remove_areas"
SYNTHETIC_ALERT_ACTION: Final = "synthetic_alert"
MANUAL_EVENT_END_ACTION: Final = "manual_event_end"
OREF_ALERT_UNIQUE_ID: Final = DOMAIN
ALL_AREAS_ID_SUFFIX: Final = "all_areas"
TIME_TO_SHELTER_ID_SUFFIX: Final = "time_to_shelter"
LOCATION_ID_SUFFIX: Final = "location"
AREAS_TEMPLATE_FUNCTION: Final = "oref_areas"
DISTRICT_TEMPLATE_FUNCTION: Final = "oref_district"
COORDINATE_TEMPLATE_FUNCTION: Final = "oref_coordinate"
SHELTER_TEMPLATE_FUNCTION: Final = "oref_shelter"
ICON_TEMPLATE_FUNCTION: Final = "oref_icon"
EMOJI_TEMPLATE_FUNCTION: Final = "oref_emoji"
DISTANCE_TEMPLATE_FUNCTION: Final = "oref_distance"
DISTANCE_TEST_TEMPLATE_FUNCTION: Final = "oref_test_distance"
FIND_AREA_TEMPLATE_FUNCTION: Final = "oref_find_area"
POLYGON_TEMPLATE_FUNCTION: Final = "oref_polygon"
ALERTS_TEMPLATE_FUNCTION: Final = "oref_alerts"

AREA_FIELD: Final = "data"
CATEGORY_FIELD: Final = "category"
CHANNEL_FIELD: Final = "channel"
DATE_FIELD: Final = "alertDate"
TITLE_FIELD: Final = "title"

MANUAL_EVENT_END_TITLE: Final = "האירוע סומן כהסתיים ידנית"


@dataclass(frozen=True)
class Record:
    """Record type."""

    data: str
    category: int
    channel: str
    alertDate: str  # noqa: N815
    title: str

    def __post_init__(self) -> None:
        """Convert StrEnum to plain str."""
        if isinstance(self.channel, enum.StrEnum):
            object.__setattr__(self, "channel", self.channel.value)


class RecordType(enum.StrEnum):
    """Event types."""

    PRE_ALERT = "pre_alert"
    ALERT = "alert"
    END = "end"


@dataclass(frozen=True)
class RecordAndMetadata:
    """Class for holding a record with additional metadata."""

    raw: Record
    raw_dict: dict[str, str | int] = field(hash=False, compare=False)
    time: datetime = field(hash=False, compare=False)
    record_type: RecordType | None = field(hash=False, compare=False)
    expire: datetime | None = field(hash=False, compare=False)


class RecordSource(enum.StrEnum):
    """Enum for alert sources."""

    HISTORY = "website-history"
    MOBILE = "mobile"
    TZEVAADOM = "tzevaadom"
    SYNTHETIC = "synthetic"
    WEBSITE = "website"
