"""Test utils."""
import json
import os
from typing import Any

from pytest_homeassistant_custom_component.common import load_fixture
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.oref_alert.coordinator import OREF_ALERTS_URL, OREF_HISTORY_URL


def mock_urls(
    aioclient_mock: AiohttpClientMocker,
    real_time_fixture: str | None,
    history_fixture: str | None,
    **kwargs: Any,
) -> None:
    """Mock the URLs."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        OREF_ALERTS_URL,
        text=load_fixture(real_time_fixture) if real_time_fixture else "",
        **kwargs,
    )
    aioclient_mock.get(
        OREF_HISTORY_URL,
        text=load_fixture(history_fixture) if history_fixture else "",
        **kwargs,
    )


def fixture_path(file_name: str) -> str:
    """Return absolute path of a fixture file."""
    return os.path.join(
        f"{os.path.dirname(os.path.abspath(__file__))}/fixtures",
        file_name,
    )


def load_json_fixture(file_name: str) -> Any:
    """Return a json object from a local fixture file."""
    with open(
        fixture_path(file_name),
        encoding="utf-8",
    ) as file:
        return json.load(file)
