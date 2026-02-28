"""Alert categories metadata."""

from __future__ import annotations

from typing import Final

# Based on the content of: https://www.oref.org.il/alerts/alertCategories.json

# Each category contains: (icon, emoji, is_alert)
CATEGORY_METADATA: Final = {
    1: ("rocket-launch", "🚀", True),  # missilealert
    2: ("airplane-alert", "✈️", True),  # uav
    3: ("chemical-weapon", "☢️", True),  # nonconventional
    4: ("alert", "🚨", True),  # warning
    5: ("firework", "🎆", False),  # memorialday1
    6: ("firework", "🎆", False),  # memorialday2
    7: ("earth", "🌍", True),  # earthquakealert1
    8: ("earth", "🌍", True),  # earthquakealert2
    9: ("nuke", "☢️", True),  # cbrne
    10: ("shield-home", "⚔️", True),  # terrorattack
    11: ("home-flood", "🌊", True),  # tsunami
    12: ("biohazard", "☣️", True),  # hazmat
    13: ("message-alert", "⚠", False),  # update
    14: ("flash-alert", "⚡", False),  # flash
    15: ("alert-circle-check", "✅", False),  # missilealertdrill
    16: ("alert-circle-check", "✅", False),  # uavdrill
    17: ("alert-circle-check", "✅", False),  # nonconventionaldrill
    18: ("alert-circle-check", "✅", False),  # warningdrill
    19: ("alert-circle-check", "✅", False),  # memorialdaydrill1
    20: ("alert-circle-check", "✅", False),  # memorialdaydrill2
    21: ("alert-circle-check", "✅", False),  # earthquakedrill1
    22: ("alert-circle-check", "✅", False),  # earthquakedrill2
    23: ("alert-circle-check", "✅", False),  # cbrnedrill
    24: ("alert-circle-check", "✅", False),  # terrorattackdrill
    25: ("alert-circle-check", "✅", False),  # tsunamidrill
    26: ("alert-circle-check", "✅", False),  # hazmatdrill
    27: ("alert-circle-check", "✅", False),  # updatedrill
    28: ("alert-circle-check", "✅", False),  # flashdrill
}

DEFAULT_CATEGORY: Final = CATEGORY_METADATA[4]
PRE_ALERT_CATEGORY: Final = 14
END_ALERT_CATEGORY: Final = 13
UPDATE_CATEGORIES: Final = {PRE_ALERT_CATEGORY, END_ALERT_CATEGORY}
FIRST_DRILL_CATEGORY: Final = 15

# Reverse engineered mapping from real-time to history categories.
# Look for '"aircraftIntrusion"' in the code of https://www.oref.org.il/
# The first category-to-icon mapping is for real-time categories,
# and the following mapping is for history categories.
REAL_TIME_TO_HISTORY_CATEGORY: Final = {
    1: 1,  # missile
    3: 7,  # earthquake
    4: 9,  # radiological
    5: 11,  # tsunami
    6: 2,  # aircraftIntrusion
    7: 12,  # hazardousMaterials
    13: 10,  # terroristInfiltration
}

# Reverse engineered mapping from Pushy "threatId" to history categories.
# Look for 'HazardousMaterials("1")' in the decompile code of the Android APK.
PUSHY_THREAD_ID_TO_HISTORY_CATEGORY: Final = {
    0: 1,  # Missiles
    1: 12,  # HazardousMaterials
    2: 10,  # TerroristInfiltration
    3: 7,  # Earthquake
    4: 11,  # Tsunami
    5: 2,  # AircraftPenetration
    6: 9,  # RadiologicalEvent
    9: 8,  # Earthquake2
    11: 3,  # UnconventionalMissile
}

# Based on information provided by Tzeva Adom team.
TZEVAADOM_THREAT_ID_TO_HISTORY_CATEGORY: Final = {
    0: 1,  # ירי טילים
    1: 12,  # אירוע חומרים מסוכנים
    2: 10,  # חשש לחדירת מחבלים
    3: 7,  # רעידת אדמה
    4: 11,  # חשש לצונאמי
    5: 2,  # חדירת כלי טיס עוין  # noqa: RUF003
    6: 9,  # חשש לאירוע רדיולוגי
    7: 3,  # ירי בלתי קונבנציונלי (כימי)
    8: 4,  # התרעה כללית גנרית
}


def category_metadata(category: int) -> tuple[str, str, bool]:
    """Return the metadata for the category."""
    return CATEGORY_METADATA.get(category, DEFAULT_CATEGORY)


def category_to_icon(category: int) -> str:
    """Return mdi icon for the category."""
    return f"mdi:{category_metadata(category)[0]}"


def category_to_emoji(category: int) -> str:
    """Return emoji for the category."""
    return category_metadata(category)[1]


def category_is_alert(category: int) -> bool:
    """Return the alert category."""
    return 0 < category < FIRST_DRILL_CATEGORY and category_metadata(category)[2]


def category_is_update(category: int) -> bool:
    """Check if category is update."""
    return category in UPDATE_CATEGORIES


def real_time_to_history_category(category: int) -> int | None:
    """Return the history category for the real-time category."""
    return REAL_TIME_TO_HISTORY_CATEGORY.get(category)


def pushy_thread_id_to_history_category(category: int) -> int | None:
    """Return the history category for Pushy thread ID."""
    return PUSHY_THREAD_ID_TO_HISTORY_CATEGORY.get(category)


def tzevaadom_threat_id_to_history_category(category: int) -> int | None:
    """Return the history category for Tzeva Adom threat ID."""
    return TZEVAADOM_THREAT_ID_TO_HISTORY_CATEGORY.get(category)
