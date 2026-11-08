"""Publish JS custom cards."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Final

import homeassistant.util.dt as dt_util
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import (  # type: ignore[attr-defined]
    StaticPathConfig,  # pyright: ignore[reportPrivateImportUsage]
)
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .metadata.area_to_polygon import POLYGONS_FILE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

FRONTEND_PATH: Final = Path(__file__).parent / "cards"
MAP_CARD_FILE: Final = "oref-alert-map.js"
URL_BASE: Final = f"/{DOMAIN}_internal_static"
# Loaded on demand by the map card (POLYGONS_URL in oref-alert-map.js).
# A release ships only the .gz version, which is served as-is (browsers
# always accept gzip).
POLYGONS_URL: Final = f"/{DOMAIN}_polygons.json"


async def publish_cards(hass: HomeAssistant) -> str:
    """Publish the custom cards."""
    _, integration = await asyncio.gather(
        hass.http.async_register_static_paths(
            [
                StaticPathConfig(URL_BASE, str(FRONTEND_PATH), cache_headers=True),
                StaticPathConfig(POLYGONS_URL, str(POLYGONS_FILE), cache_headers=True),
            ]
        ),
        async_get_integration(hass, DOMAIN),
    )

    if integration.version and integration.version != "1.0.0":
        version = str(integration.version)
    else:
        version = str(int(dt_util.now().timestamp()))

    add_extra_js_url(hass, f"{URL_BASE}/{MAP_CARD_FILE}?v={version}")

    return version
