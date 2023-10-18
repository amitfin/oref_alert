"""Constants for the oref_alert integration."""
import logging
from typing import Final

DOMAIN: Final = "oref_alert"
LOGGER = logging.getLogger(__package__)

ATTR_COUNTRY_ALERTS: Final = "country_alerts"
ATTR_COUNTRY_ACTIVE_ALERTS: Final = "country_active_alerts"
ATTR_SELECTED_AREAS_ALERTS: Final = "selected_areas_alerts"
ATTR_SELECTED_AREAS_ACTIVE_ALERTS: Final = "selected_areas_active_alerts"
CONF_AREAS: Final = "areas"
CONF_ALERT_MAX_AGE: Final = "alert_max_age"
DEFAULT_ALERT_MAX_AGE: Final = 10
