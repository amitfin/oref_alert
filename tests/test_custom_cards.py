"""The tests for the custom_cards file."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from homeassistant.components.http import (  # type: ignore[attr-defined]
    StaticPathConfig,  # pyright: ignore[reportPrivateImportUsage]
)
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.oref_alert import custom_cards
from custom_components.oref_alert.const import CONF_AREAS, DOMAIN
from custom_components.oref_alert.metadata.area_to_polygon import POLYGONS_FILE

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant.typing import ClientSessionGenerator

DEFAULT_OPTIONS: dict[str, list[str]] = {CONF_AREAS: []}


async def test_setup_js_url(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test setup registers extra JS URL with a deterministic cache-busting value."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    freezer.move_to(now)
    ts = int(now.timestamp())

    with patch(
        "custom_components.oref_alert.custom_cards.add_extra_js_url"
    ) as mock_add_extra_js_url:
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

    mock_add_extra_js_url.assert_called_once_with(
        hass, f"/oref_alert_internal_static/oref-alert-map.js?v={ts}"
    )


async def test_publish_cards_uses_integration_version_when_not_dev() -> None:
    """Test publish_cards uses integration version outside dev mode."""
    fake_hass = SimpleNamespace(
        http=SimpleNamespace(async_register_static_paths=AsyncMock())
    )
    integration = SimpleNamespace(version="2.3.4")

    with (
        patch(
            "custom_components.oref_alert.custom_cards.add_extra_js_url"
        ) as mock_add_extra_js_url,
        patch(
            "custom_components.oref_alert.custom_cards.async_get_integration",
            new=AsyncMock(return_value=integration),
        ),
    ):
        version = await custom_cards.publish_cards(fake_hass)  # pyright: ignore[reportArgumentType]

    mock_add_extra_js_url.assert_called_once_with(
        fake_hass, "/oref_alert_internal_static/oref-alert-map.js?v=2.3.4"
    )
    assert version == "2.3.4"
    fake_hass.http.async_register_static_paths.assert_awaited_once_with(
        [
            StaticPathConfig(
                "/oref_alert_internal_static",
                str(custom_cards.FRONTEND_PATH),
                cache_headers=True,
            ),
            StaticPathConfig(
                "/oref_alert_polygons.json",
                str(POLYGONS_FILE),
                cache_headers=True,
            ),
        ]
    )


def test_map_card_uses_polygons_url() -> None:
    """Test the map card fetches the URL the polygons are served at."""
    card = (custom_cards.FRONTEND_PATH / custom_cards.MAP_CARD_FILE).read_text(
        encoding="utf-8"
    )
    assert f'const POLYGONS_URL = "{custom_cards.POLYGONS_URL}";' in card


async def test_polygons_served_from_gz_only(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a release (only the .gz file) serves the polygons to browsers."""
    content = b'{\n"Area A":[[1.5,2.5],[3,4]]\n}\n'
    (tmp_path / "area_to_polygon.json.gz").write_bytes(gzip.compress(content))
    monkeypatch.setattr(
        custom_cards, "POLYGONS_FILE", tmp_path / "area_to_polygon.json"
    )
    assert await async_setup_component(hass, "http", {})

    with patch("custom_components.oref_alert.custom_cards.add_extra_js_url"):
        await custom_cards.publish_cards(hass)
    client = await hass_client_no_auth()

    response = await client.get(
        f"{custom_cards.POLYGONS_URL}?v=1", headers={"Accept-Encoding": "gzip"}
    )
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Content-Encoding"] == "gzip"
    assert "max-age" in response.headers["Cache-Control"]
    assert await response.read() == content
