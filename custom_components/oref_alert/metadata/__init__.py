"""Metadata from Oref backend."""

from typing import Any, Final

ALL_AREAS_ALIASES: Final = {"כל הארץ", "ברחבי הארץ"}

OREF_HEADERS: Final = {
    "Referer": "https://www.oref.org.il/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}

SEGMENTS_URL: Final = "https://dist-android.meser-hadash.org.il/smart-dist/services/anonymous/segments/android?instance=1544803905&locale=iw_IL"
SEGMENTS_TEST_AREA: Final = "בדיקה"
DEPRECATION_SUFFIX: Final = " (אזור התרעה ישן)"

TZEVAADOM_SPELLING_FIX: Final = {
    "אשדוד -יא,יב,טו,יז,מרינה,סיט": "אשדוד -יא,יב,טו,יז,מרינה,סיטי"
}

SOME_PARTS_OF_THE_COUNTRY = "בחלק מהאזורים בארץ"


def is_area_segment(segment: dict[str, Any]) -> bool:
    """Check if a segment represents an area."""
    return not segment.get("isParent") and segment["name"] != SEGMENTS_TEST_AREA
