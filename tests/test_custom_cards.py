"""The tests for the custom_cards file."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import brotli
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert import custom_cards
from custom_components.oref_alert.const import CONF_AREAS, DOMAIN

if TYPE_CHECKING:
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

    mock_add_extra_js_url.assert_called_once_with(
        hass, f"/oref_alert_internal_static/oref-alert-map.js?v={ts}"
    )


def _read_and_verify(name: Path) -> bytes:
    """Return the file's content, verifying its compressed versions are identical."""
    raw = name.read_bytes()
    gz = gzip.decompress(Path(f"{name}.gz").read_bytes())
    br = brotli.decompress(Path(f"{name}.br").read_bytes())
    assert raw == gz == br
    return raw


async def test_update_files_writes_then_skips_then_rewrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test _update_files creates, skips and updates the files."""
    name = tmp_path / "file.json"
    compress = Mock(wraps=brotli.compress)
    monkeypatch.setattr(brotli, "compress", compress)

    await custom_cards._update_files(name, b"first")  # noqa: SLF001
    assert _read_and_verify(name) == b"first"
    assert compress.call_count == 1

    await custom_cards._update_files(name, b"first")  # noqa: SLF001
    assert _read_and_verify(name) == b"first"
    assert compress.call_count == 1

    await custom_cards._update_files(name, b"second")  # noqa: SLF001
    assert _read_and_verify(name) == b"second"
    assert compress.call_count == 2


@pytest.mark.parametrize("suffix", [".gz", ".br"])
async def test_update_files_restores_missing_compressed_file(
    tmp_path: Path, suffix: str
) -> None:
    """Test a missing compressed file is created even if the content is the same."""
    name = tmp_path / "file.json"
    await custom_cards._update_files(name, b"data")  # noqa: SLF001
    Path(f"{name}{suffix}").unlink()  # noqa: ASYNC240

    await custom_cards._update_files(name, b"data")  # noqa: SLF001
    assert _read_and_verify(name) == b"data"


async def test_create_polygons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _create_polygons writes the polygons as JSON."""
    monkeypatch.setattr(custom_cards, "FRONTEND_PATH", tmp_path)

    async def polygons() -> dict[str, list[list[int]]]:
        return {"Area A": [[1, 2], [3, 4]]}

    monkeypatch.setattr(custom_cards, "init_area_to_polygon", polygons)

    await custom_cards._create_polygons()  # noqa: SLF001
    content = _read_and_verify(tmp_path / custom_cards.POLYGONS_FILE)
    assert json.loads(content) == {"Area A": [[1, 2], [3, 4]]}


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
        version = await custom_cards.publish_cards(fake_hass)  # pyright: ignore[reportArgumentType]

    mock_add_extra_js_url.assert_called_once_with(
        fake_hass, "/oref_alert_internal_static/oref-alert-map.js?v=2.3.4"
    )
    assert version == "2.3.4"
