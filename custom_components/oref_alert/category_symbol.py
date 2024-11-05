"""Map categories to icons and emojis."""

# Based on the content of: https://www.oref.org.il/alerts/alertCategories.json

CATEGORY_TO_ICON_EMOJI = {
    1: ("rocket-launch", "🚀"),  # missilealert
    2: ("airplane-alert", "✈️"),  # uav
    3: ("chemical-weapon", "☢️"),  # nonconventional
    4: ("alert", "🚨"),  # warning
    5: ("firework", "🎆"),  # memorialday1
    6: ("firework", "🎆"),  # memorialday2
    7: ("earth", "🌍"),  # earthquakealert1
    8: ("earth", "🌍"),  # earthquakealert2
    9: ("nuke", "☢️"),  # cbrne
    10: ("shield-home", "⚔️"),  # terrorattack
    11: ("home-flood", "🌊"),  # tsunami
    12: ("biohazard", "☣️"),  # hazmat
    13: ("update", "🔄"),  # update
    14: ("flash-alert", "⚡"),  # flash
    15: ("alert-circle-check", "✅"),  # missilealertdrill
    16: ("alert-circle-check", "✅"),  # uavdrill
    17: ("alert-circle-check", "✅"),  # nonconventionaldrill
    18: ("alert-circle-check", "✅"),  # warningdrill
    19: ("alert-circle-check", "✅"),  # memorialdaydrill1
    20: ("alert-circle-check", "✅"),  # memorialdaydrill2
    21: ("alert-circle-check", "✅"),  # earthquakedrill1
    22: ("alert-circle-check", "✅"),  # earthquakedrill2
    23: ("alert-circle-check", "✅"),  # cbrnedrill
    24: ("alert-circle-check", "✅"),  # terrorattackdrill
    25: ("alert-circle-check", "✅"),  # tsunamidrill
    26: ("alert-circle-check", "✅"),  # hazmatdrill
    27: ("alert-circle-check", "✅"),  # updatedrill
    28: ("alert-circle-check", "✅"),  # flashdrill
}

DEFAULT_CATEGORY = 4


def category_to_icon(category: int) -> str:
    """Return mdi icon for the category."""
    if category not in CATEGORY_TO_ICON_EMOJI:
        category = DEFAULT_CATEGORY
    return f"mdi:{CATEGORY_TO_ICON_EMOJI[category][0]}"


def category_to_emoji(category: int) -> str:
    """Return emoji for the category."""
    if category not in CATEGORY_TO_ICON_EMOJI:
        category = DEFAULT_CATEGORY
    return CATEGORY_TO_ICON_EMOJI[category][1]
