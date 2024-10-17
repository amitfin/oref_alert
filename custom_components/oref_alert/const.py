"""Constants for the oref_alert integration."""

import logging
import zoneinfo
from typing import Final

DOMAIN: Final = "oref_alert"
TITLE: Final = "Oref Alert"
LOGGER = logging.getLogger(__package__)
DATA_COORDINATOR: Final = "coordinator"
IST = zoneinfo.ZoneInfo("Asia/Jerusalem")

ATTR_ALERT: Final = "alert"
ATTR_AREA: Final = "area"
ATTR_COUNTRY_ALERTS: Final = "country_alerts"
ATTR_COUNTRY_ACTIVE_ALERTS: Final = "country_active_alerts"
ATTR_HOME_DISTANCE: Final = "home_distance"
ATTR_SELECTED_AREAS_ALERTS: Final = "selected_areas_alerts"
ATTR_SELECTED_AREAS_ACTIVE_ALERTS: Final = "selected_areas_active_alerts"
ATTR_TIME_TO_SHELTER: Final = "time_to_shelter"

CONF_AREA: Final = "area"
CONF_AREAS: Final = "areas"
CONF_ALERT_ACTIVE_DURATION: Final = "alert_active_duration"
CONF_ALERT_MAX_AGE_DEPRECATED: Final = "alert_max_age"
CONF_DURATION: Final = "duration"
CONF_OFF_ICON: Final = "off_icon"
CONF_ON_ICON: Final = "on_icon"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_SENSORS: Final = "sensors"

DEFAULT_ALERT_ACTIVE_DURATION: Final = 10
DEFAULT_ON_ICON: Final = "mdi:home-alert-outline"
DEFAULT_OFF_ICON: Final = "mdi:home-outline"
DEFAULT_POLL_INTERVAL: Final = 2

ADD_SENSOR_SERVICE: Final = "add_sensor"
REMOVE_SENSOR_SERVICE: Final = "remove_sensor"
SYNTHETIC_ALERT_SERVICE: Final = "synthetic_alert"
OREF_ALERT_UNIQUE_ID: Final = DOMAIN
ALL_AREAS_ID_SUFFIX: Final = "all_areas"
ALL_AREAS_NAME_SUFFIX: Final = "All Areas"
END_TIME_ID_SUFFIX: Final = "end_time"
END_TIME_NAME_SUFFIX: Final = "End Time"
TIME_TO_SHELTER_ID_SUFFIX: Final = "time_to_shelter"
TIME_TO_SHELTER_NAME_SUFFIX: Final = "Time To Shelter"
LOCATION_ID_SUFFIX: Final = "location"
