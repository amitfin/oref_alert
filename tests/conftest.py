"""Global fixtures."""

# Fixtures allow you to replace functions with a Mock object. You can perform
# many options via the Mock to reflect a particular behavior from the original
# function that you want to see without going through the function's actual logic.
# Fixtures can either be passed into tests as parameters, or if autouse=True, they
# will automatically be used across all tests.
#
# Fixtures that are defined in conftest.py are available across all tests. You can also
# define fixtures within a particular test file to scope them locally.
#
# pytest_homeassistant_custom_component provides some fixtures that are provided by
# Home Assistant core. You can find those fixture definitions here:
# https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/blob/master/pytest_homeassistant_custom_component/common.py
#
# See here for more info: https://docs.pytest.org/en/latest/fixture.html (note that
# pytest includes fixtures OOB which you can use as defined on this page)

from asyncio import Event
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import WSMessage, WSMsgType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .utils import mock_urls


# This fixture enables loading custom integrations in all tests.
# Remove to enable selective use of this fixture
@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations: bool) -> None:  # noqa: ARG001, FBT001
    """Enable loading custom components."""
    return


@pytest.fixture(autouse=True)
def _no_platform_errors_in_log(caplog: pytest.LogCaptureFixture) -> Generator[None]:
    """Ensure no platform errors are logged."""
    yield
    for record in caplog.get_records(when="call"):
        message = record.getMessage()
        assert record.levelname != "ERROR" or "platform oref_alert" not in message, (
            f"Error found in log: {message}"
        )


@pytest.fixture(autouse=True)
def _auto_aioclient_mock(aioclient_mock: AiohttpClientMocker) -> None:
    """Mock aiohttp with empty result relevant URLs."""
    mock_urls(aioclient_mock, None, None)


@pytest.fixture(autouse=True)
def _disable_asyncio_sleep() -> Generator[None]:
    """Disable sleep for all tests."""
    with patch("asyncio.sleep"):
        yield


@pytest.fixture(autouse=True)
def _mock_ws() -> Generator[None]:
    """Mock WebSocket connection."""
    ws_closed = Event()

    async def mock_receive() -> WSMessage:
        await ws_closed.wait()
        return WSMessage(type=WSMsgType.CLOSED, data="{}", extra=None)

    ws = AsyncMock()
    ws.receive = mock_receive
    ws.close = AsyncMock(side_effect=lambda: ws_closed.set())

    with patch(
        "aiohttp.ClientSession.ws_connect",
        new=lambda *_, **__: AsyncMock(__aenter__=AsyncMock(return_value=ws)),
    ) as _:
        yield
