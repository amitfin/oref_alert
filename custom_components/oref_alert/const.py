"""Constants for the oref_alert integration."""

import enum
import logging
import zoneinfo
from typing import Final, TypedDict

DOMAIN: Final = "oref_alert"
TITLE: Final = "Oref Alert"
LOGGER = logging.getLogger(__package__)
IST = zoneinfo.ZoneInfo("Asia/Jerusalem")

ATTR_ALERT: Final = "alert"
ATTR_AREA: Final = "area"
ATTR_COUNTRY_ALERTS: Final = "country_alerts"
ATTR_COUNTRY_ACTIVE_ALERTS: Final = "country_active_alerts"
ATTR_COUNTRY_UPDATES: Final = "country_updates"
ATTR_DISPLAY: Final = "display"
ATTR_EMOJI: Final = "emoji"
ATTR_HOME_DISTANCE: Final = "home_distance"
ATTR_SELECTED_AREAS_ALERTS: Final = "selected_areas_alerts"
ATTR_SELECTED_AREAS_ACTIVE_ALERTS: Final = "selected_areas_active_alerts"
ATTR_SELECTED_AREAS_UPDATES: Final = "selected_areas_updates"
ATTR_TIME_TO_SHELTER: Final = "time_to_shelter"

CONF_AREA: Final = "area"
CONF_AREAS: Final = "areas"
CONF_ALERT_ACTIVE_DURATION: Final = "alert_active_duration"
CONF_ALERT_MAX_AGE_DEPRECATED: Final = "alert_max_age"
CONF_ALL_ALERTS_ATTRIBUTES: Final = "all_alerts_attributes"
CONF_DURATION: Final = "duration"
CONF_SENSORS: Final = "sensors"

DEFAULT_ALERT_ACTIVE_DURATION: Final = 10

ADD_SENSOR_ACTION: Final = "add_sensor"
REMOVE_SENSOR_ACTION: Final = "remove_sensor"
EDIT_SENSOR_ACTION: Final = "edit_sensor"
ADD_AREAS: Final = "add_areas"
REMOVE_AREAS: Final = "remove_areas"
SYNTHETIC_ALERT_ACTION: Final = "synthetic_alert"
OREF_ALERT_UNIQUE_ID: Final = DOMAIN
ALL_AREAS_ID_SUFFIX: Final = "all_areas"
END_TIME_ID_SUFFIX: Final = "end_time"
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

AREA_FIELD: Final = "data"
CATEGORY_FIELD: Final = "category"
CHANNEL_FIELD: Final = "channel"
DATE_FIELD: Final = "alertDate"
TITLE_FIELD: Final = "title"


class AlertType(TypedDict):
    """Type for area info."""

    data: str
    category: int
    channel: str
    alertDate: str
    title: str


class AlertSource(str, enum.Enum):
    """Enum for alert sources."""

    HISTORY = "website-history"
    MOBILE = "mobile"
    TZEVAADOM = "tzevaadom"
    SYNTHETIC = "synthetic"
    WEBSITE = "website"
