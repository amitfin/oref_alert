"""The tests for the custom_cards file."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, call, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert import custom_cards
from custom_components.oref_alert.const import CONF_AREAS, DOMAIN

if TYPE_CHECKING:
    from pathlib import Path

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

DEFAULT_OPTIONS: dict[str, list[str]] = {CONF_AREAS: []}


@pytest.fixture(autouse=True)
def _disable_custom_cards_file_write() -> None:
    """Override global fixture so this module can test real polygon generation."""
    return


async def test_setup_js_url(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test setup registers extra JS URL with a deterministic cache-busting value."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    freezer.move_to(now)
    ts = int(now.timestamp())

    with (
        patch(
            "custom_components.oref_alert.custom_cards.add_extra_js_url"
        ) as mock_add_extra_js_url,
        patch(
            "custom_components.oref_alert.custom_cards._create_polygons",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

    mock_add_extra_js_url.assert_has_calls(
        [
            call(hass, f"/oref_alert_internal_static/oref-alert-polygons.js?v={ts}"),
            call(hass, f"/oref_alert_internal_static/oref-alert-map.js?v={ts}"),
        ]
    )
    assert mock_add_extra_js_url.call_count == 2


async def test_create_polygons_writes_then_skips_then_rewrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test _create_polygons file creation and update behavior."""
    monkeypatch.setattr(custom_cards, "FRONTEND_PATH", tmp_path)

    async def polygons_v1() -> dict[str, list[list[int]]]:
        return {"Area A": [[1, 2], [3, 4]]}

    monkeypatch.setattr(custom_cards, "init_area_to_polygon", polygons_v1)

    await custom_cards._create_polygons()  # noqa: SLF001
    out_file = tmp_path / custom_cards.POLYGONS_CARD_FILE
    first = out_file.read_text()
    assert '"Area A":[[1,2],[3,4]]' in first

    await custom_cards._create_polygons()  # noqa: SLF001
    second = out_file.read_text()
    assert second == first

    async def polygons_v2() -> dict[str, list[list[int]]]:
        return {"Area A": [[9, 9]], "Area B": [[8, 8]]}

    monkeypatch.setattr(custom_cards, "init_area_to_polygon", polygons_v2)
    await custom_cards._create_polygons()  # noqa: SLF001
    third = out_file.read_text()
    assert third != first
    assert '"Area B":[[8,8]]' in third


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
            "custom_components.oref_alert.custom_cards._create_polygons",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.oref_alert.custom_cards.async_get_integration",
            new=AsyncMock(return_value=integration),
        ),
    ):
        await custom_cards.publish_cards(fake_hass)  # pyright: ignore[reportArgumentType]

    mock_add_extra_js_url.assert_has_calls(
        [
            call(
                fake_hass, "/oref_alert_internal_static/oref-alert-polygons.js?v=2.3.4"
            ),
            call(fake_hass, "/oref_alert_internal_static/oref-alert-map.js?v=2.3.4"),
        ]
    )
    assert mock_add_extra_js_url.call_count == 2
