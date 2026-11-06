#!/usr/bin/env python3
"""Check the endpoints the integration uses at runtime."""

import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlencode

import aiohttp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

sys.path.insert(
    0,
    str((Path(__file__).parent.parent / "custom_components" / "oref_alert").resolve()),
)

from metadata import (  # pyright: ignore[reportMissingImports]
    OREF_ALERTS_URL,
    OREF_HEADERS,
    OREF_HISTORY2_URL,
    OREF_HISTORY_URL,
    SEGMENTS_URL,
    TZEVAADOM_ORIGIN,
    TZEVAADOM_WS_URL,
    is_area_segment,
)

HISTORY_FIELDS = {"alertDate", "title", "data", "category"}
HISTORY2_FIELDS = {"data", "date", "time", "dateTime", "category", "category_Desc"}
# A past minute with more than 200 alerts (a full page), to check the paging.
HISTORY2_BUSY_MINUTE_URL = (
    f"{OREF_HISTORY2_URL.split('?')[0]}"
    "?from=2025-06-13T22:11:00&to=2025-06-13T22:11:59&cities="
)
TIMEOUT = aiohttp.ClientTimeout(total=30)
ATTEMPTS = 3
RETRY_DELAY = 30


async def fetch_json(session: aiohttp.ClientSession, url: str) -> Any:
    """Fetch URL and return its JSON content (or None for an empty reply)."""
    async with session.get(
        url, headers=OREF_HEADERS if "oref.org.il" in url else None
    ) as response:
        response.raise_for_status()
        text = (await response.read()).decode("utf-8-sig").replace("\x00", "").strip()
        return json.loads(text) if text else None


def history2_records(payload: Any) -> list[dict[str, Any]]:
    """Return the records of a history2 reply, after checking its format."""
    assert isinstance(payload, dict), payload
    assert isinstance(payload["alarmsGroupedByDate"], list), payload
    records = [
        record for group in payload["alarmsGroupedByDate"] for record in group["value"]
    ]
    for record in records:
        assert set(record) >= HISTORY2_FIELDS, record
    return records


async def check_alerts(session: aiohttp.ClientSession) -> None:
    """Check the real-time alerts."""
    payload = await fetch_json(session, OREF_ALERTS_URL)
    assert payload is None or isinstance(payload.get("data"), list), payload


async def check_history(session: aiohttp.ClientSession) -> None:
    """Check the alerts history."""
    payload = await fetch_json(session, OREF_HISTORY_URL)
    assert isinstance(payload or [], list), payload
    for record in payload or []:
        assert set(record) >= HISTORY_FIELDS, record


async def check_history2(session: aiohttp.ClientSession) -> None:
    """Check the alerts history of the last day."""
    history2_records(await fetch_json(session, OREF_HISTORY2_URL))


async def check_history2_paging(session: aiohttp.ClientSession) -> None:
    """Check the paging of the alerts history."""
    first = history2_records(await fetch_json(session, HISTORY2_BUSY_MINUTE_URL))
    assert first, "No records in the busy minute"
    last = first[-1]
    second = history2_records(
        await fetch_json(
            session,
            f"{HISTORY2_BUSY_MINUTE_URL}&"
            + urlencode(
                {
                    "lastCreatedOn": last["dateTime"],
                    "lastTitle": last["category_Desc"],
                    "lastCityName": last["data"],
                },
                quote_via=quote,
            ),
        )
    )
    assert second, "The second page is empty"
    assert second[-1] != last, "Paging doesn't move forward"


async def check_segments(session: aiohttp.ClientSession) -> None:
    """Check the segments (the list of areas)."""
    payload = await fetch_json(session, SEGMENTS_URL)
    segments = payload["segments"].values()
    assert any(is_area_segment(segment) for segment in segments), payload


async def check_tzevaadom(session: aiohttp.ClientSession) -> None:
    """Check the connection to Tzeva Adom."""
    async with session.ws_connect(TZEVAADOM_WS_URL, origin=TZEVAADOM_ORIGIN):
        pass


CHECKS: list[Callable[[aiohttp.ClientSession], Awaitable[None]]] = [
    check_alerts,
    check_history,
    check_history2,
    check_history2_paging,
    check_segments,
    check_tzevaadom,
]


async def run_check(
    session: aiohttp.ClientSession,
    check: Callable[[aiohttp.ClientSession], Awaitable[None]],
) -> bool:
    """Run a check (with retries) and return whether it passed."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            await check(session)
        except Exception as ex:  # noqa: BLE001
            print(  # noqa: T201
                f"FAIL {check.__name__} ({attempt}/{ATTEMPTS}): "
                f"{type(ex).__name__}: {ex}",
                flush=True,
            )
            if attempt < ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY)
        else:
            print(f"OK   {check.__name__}", flush=True)  # noqa: T201
            return True
    return False


async def main() -> int:
    """Run all checks and return the number of failures."""
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        return sum([not await run_check(session, check) for check in CHECKS])


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
