"""Publish JS custom cards."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

import aiofiles
import aiofiles.os
import brotli
import homeassistant.util.dt as dt_util
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import (  # type: ignore[attr-defined]
    StaticPathConfig,  # pyright: ignore[reportPrivateImportUsage]
)
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .metadata.area_to_polygon import init_area_to_polygon

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

FRONTEND_PATH: Final = Path(__file__).parent / "cards"
MAP_CARD_FILE: Final = "oref-alert-map.js"
POLYGONS_FILE: Final = "oref-alert-polygons.json"
URL_BASE: Final = f"/{DOMAIN}_internal_static"


async def _write(name: Path, data: bytes) -> None:
    """Write the data to the file."""
    async with aiofiles.open(name, "wb") as file:
        await file.write(data)


async def _update_files(name: Path, data: bytes) -> None:
    """
    Write the file and its pre-compressed versions (.gz and .br), if needed.

    Home Assistant doesn't compress static files, but it serves the
    pre-compressed versions when the browser accepts them.
    """
    gz_name = Path(f"{name}.gz")
    br_name = Path(f"{name}.br")

    if (
        await aiofiles.os.path.isfile(name)
        and await aiofiles.os.path.isfile(gz_name)
        and await aiofiles.os.path.isfile(br_name)
    ):
        async with aiofiles.open(name, "rb") as file:
            if await file.read() == data:
                return

    gz, br = await asyncio.gather(
        asyncio.to_thread(gzip.compress, data, 9, mtime=0),
        asyncio.to_thread(brotli.compress, data, quality=11),
    )
    await _write(name, data)
    await _write(gz_name, gz)
    await _write(br_name, br)


async def _create_polygons() -> None:
    """Create the polygons file (loaded on demand by the map card)."""
    polygons = await init_area_to_polygon()
    await _update_files(
        FRONTEND_PATH / POLYGONS_FILE,
        json.dumps(polygons, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )


async def publish_cards(hass: HomeAssistant) -> str:
    """Publish the custom cards."""
    _, _, integration = await asyncio.gather(
        _create_polygons(),
        hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(FRONTEND_PATH), cache_headers=True)]
        ),
        async_get_integration(hass, DOMAIN),
    )

    if integration.version and integration.version != "1.0.0":
        version = str(integration.version)
    else:
        version = str(int(dt_util.now().timestamp()))

    add_extra_js_url(hass, f"{URL_BASE}/{MAP_CARD_FILE}?v={version}")

    return version
