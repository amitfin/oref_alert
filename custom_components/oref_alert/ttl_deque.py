"""Implementation of queue with TTL."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any

import homeassistant.util.dt as dt_util


class TTLDeque:
    """Add items to the beginning of the list and removes items when TTL expires."""

    def __init__(self, ttl: int) -> None:
        """Initialize the deque."""
        self._ttl = timedelta(minutes=ttl)
        self._deque: deque[tuple[datetime, Any]] = deque()

    def add(self, item: Any) -> None:
        """Add an item."""
        self._deque.appendleft((dt_util.now(), item))
        self._prune()

    def _prune(self) -> None:
        """Remove expired items."""
        now = dt_util.now()
        while self._deque and now - self._deque[-1][0] >= self._ttl:
            self._deque.pop()

    def items(self) -> list[Any]:
        """Return the items."""
        self._prune()
        return [item for _, item in self._deque]

    def changed(self) -> datetime | None:
        """Return the timestamp of the 1st (most recent) item."""
        self._prune()
        return self._deque[0][0] if self._deque else None
