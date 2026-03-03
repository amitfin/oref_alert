"""Publish JS custom cards."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

import aiofiles
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .metadata.area_to_polygon import init_area_to_polygon

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

FRONTEND_PATH: Final = Path(__file__).parent / "cards"
MAP_CARD_FILE: Final = "oref-alert-map.js"
POLYGONS_CARD_FILE: Final = "oref-alert-polygons.js"
URL_BASE: Final = f"/{DOMAIN}_internal_static"

POLYGON_CARD: Final = """const _polygons = %s;

class OrefAlertPolygons extends HTMLElement {
  constructor() {
    super();
    this.polygons = _polygons;
  }
}

const elementTag = "oref-alert-polygons";
customElements.define(elementTag, OrefAlertPolygons);
customElements.whenDefined("home-assistant").then(() => {
  if (!customElements.get(elementTag)) {
    customElements.define(elementTag, OrefAlertPolygons);
  }
});
"""


async def _create_polygons() -> None:
    """Create the polygons cards."""
    file_name = FRONTEND_PATH / POLYGONS_CARD_FILE

    polygons = await init_area_to_polygon()
    content = POLYGON_CARD % json.dumps(
        polygons, ensure_ascii=False, separators=(",", ":")
    )

    if not file_name.is_file():
        previous = None
    else:
        async with aiofiles.open(file_name) as file:
            previous = await file.read()

    if content != previous:
        async with aiofiles.open(file_name, "w") as file:
            await file.write(content)


async def publish_cards(hass: HomeAssistant) -> None:
    """Publish the custom cards."""
    _, _, integration = await asyncio.gather(
        _create_polygons(),
        hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(FRONTEND_PATH), cache_headers=True)]
        ),
        async_get_integration(hass, DOMAIN),
    )

    for file_name in (POLYGONS_CARD_FILE, MAP_CARD_FILE):
        add_extra_js_url(hass, f"{URL_BASE}/{file_name}?v={integration.version or 0}")
