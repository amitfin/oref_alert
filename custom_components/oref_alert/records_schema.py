"""Record schemas."""

from __future__ import annotations

from enum import StrEnum

import voluptuous as vol

from custom_components.oref_alert import categories
from custom_components.oref_alert.const import CATEGORY_FIELD


class RecordType(StrEnum):
    """Event types."""

    PRE_ALERT = "pre_alert"
    ALERT = "alert"
    END = "end"


RECORDS_SCHEMA: dict[RecordType, vol.Schema] = {
    RecordType.PRE_ALERT: vol.Schema(
        {
            vol.Required(CATEGORY_FIELD): categories.PRE_ALERT_CATEGORY,
        },
        extra=vol.ALLOW_EXTRA,
    ),
    RecordType.END: vol.Schema(
        {
            vol.Required(CATEGORY_FIELD): categories.END_ALERT_CATEGORY,
        },
        extra=vol.ALLOW_EXTRA,
    ),
    RecordType.ALERT: vol.Schema(
        {
            vol.Required(CATEGORY_FIELD): vol.NotIn(
                (categories.PRE_ALERT_CATEGORY, categories.END_ALERT_CATEGORY)
            ),
        },
        extra=vol.ALLOW_EXTRA,
    ),
}
