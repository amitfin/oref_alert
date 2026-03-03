"""The tests for the custom_cards file."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, call, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert import custom_cards
from custom_components.oref_alert.const import CONF_AREAS, DOMAIN

if TYPE_CHECKING:
    from pathlib import Path

    from homeassistant.core import HomeAssistant

DEFAULT_OPTIONS: dict[str, list[str]] = {CONF_AREAS: []}


@pytest.fixture(autouse=True)
def _disable_custom_cards_file_write() -> None:
    """Override global fixture so this module can test real polygon generation."""
    return


async def test_setup_js_url(hass: HomeAssistant) -> None:
    """Test setup registers extra JS URL with integration version."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)

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
            call(hass, "/oref_alert_internal_static/oref-alert-polygons.js?v=1.0.0"),
            call(hass, "/oref_alert_internal_static/oref-alert-map.js?v=1.0.0"),
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
