"""Alert categories metadata."""

# Based on the content of: https://www.oref.org.il/alerts/alertCategories.json

# Each category contains: (icon, emoji, is_alert)
CATEGORY_METADATA = {
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
    14: ("flash-alert", "⚡", True),  # flash
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

DEFAULT_CATEGORY = CATEGORY_METADATA[4]
UPDATE_CATEGORY = 13


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
    return category_metadata(category)[2]


def category_is_update(category: int) -> bool:
    """Check if category is update."""
    return category == UPDATE_CATEGORY
