"""Constants for the oref_alert integration."""
import logging
from typing import Final

DOMAIN: Final = "oref_alert"
LOGGER = logging.getLogger(__package__)

CONF_CITIES: FINAL = "cities"
CONF_ALERT_MAX_AGE: FINAL = "alert_max_age"
DEFAULT_ALERT_MAX_AGE: FINAL = 300
