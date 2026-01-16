"""Metadata from Oref backend."""

from typing import Final

ALL_AREAS_ALIASES: Final = {"כל הארץ", "ברחבי הארץ"}

CITIES_MIX_URL: Final = (
    "https://alerts-history.oref.org.il/Shared/Ajax/GetCitiesMix.aspx"
)
DEPRECATION_SUFFIX: Final = " (אזור התרעה ישן)"

PUSHY_TEST_SEGMENTS: Final = [
    "5003000",
    "5003001",
    "5003002",
    "5003003",
    "5003004",
    "5003006",
]

TZEVAADOM_SPELLING_FIX: Final = {
    "אשדוד -יא,יב,טו,יז,מרינה,סיט": "אשדוד -יא,יב,טו,יז,מרינה,סיטי"
}
