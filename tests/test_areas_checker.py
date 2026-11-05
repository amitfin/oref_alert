"""The tests for the areas_checker file."""

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.oref_alert.areas_checker import CITIES_MIX_URL, AreasChecker
from custom_components.oref_alert.const import DOMAIN, OREF_HEADERS

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )


async def _areas_check(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    checker = AreasChecker(hass)
    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    checker.stop()


@pytest.mark.allowed_logs(
    [
        "The following Oref Alert areas were removed:",
        "The following Oref Alert areas were added:",
    ]
)
async def test_areas_check_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test failed areas check."""
    repairs = []
    unregister = hass.bus.async_listen(
        ir.EVENT_REPAIRS_ISSUE_REGISTRY_UPDATED,
        lambda event, repairs=repairs: repairs.append(event),
    )
    aioclient_mock.clear_requests()
    aioclient_mock.get(CITIES_MIX_URL, text='[{"label": "test"}]')
    await _areas_check(hass, freezer)
    assert "The following Oref Alert areas were removed:" in caplog.text
    assert "The following Oref Alert areas were added:" in caplog.text
    assert len(repairs) == 1
    assert repairs[0].data["action"] == "create"
    assert repairs[0].data["domain"] == DOMAIN
    assert repairs[0].data["issue_id"] == "upgrade_required"
    unregister()
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_areas_check_pass(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test successful areas check."""
    await _areas_check(hass, freezer)
    assert "The following Oref Alert areas were" not in caplog.text


async def test_areas_check_headers(hass: HomeAssistant) -> None:
    """Use the same accepted website headers for the districts request."""
    checker = AreasChecker(hass)
    with patch.object(
        checker._http_client,  # noqa: SLF001
        "get",
        wraps=checker._http_client.get,  # noqa: SLF001
    ) as get:
        await checker._check()  # noqa: SLF001
    checker.stop()
    get.assert_called_once_with(CITIES_MIX_URL, headers=OREF_HEADERS)
