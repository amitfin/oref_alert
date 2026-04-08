"""Metadata from Oref backend."""

from typing import Final

ALL_AREAS_ALIASES: Final = {"כל הארץ", "ברחבי הארץ"}

CITIES_MIX_URL: Final = (
    "https://alerts-history.oref.org.il/Shared/Ajax/GetCitiesMix.aspx"
)
DEPRECATION_SUFFIX: Final = " (אזור התרעה ישן)"

TZEVAADOM_SPELLING_FIX: Final = {
    "אשדוד -יא,יב,טו,יז,מרינה,סיט": "אשדוד -יא,יב,טו,יז,מרינה,סיטי"
}

SOME_PARTS_OF_THE_COUNTRY = "בחלק מהאזורים בארץ"
