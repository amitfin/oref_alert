"""Implementation of queue with TTL."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import homeassistant.util.dt as dt_util

if TYPE_CHECKING:
    from collections.abc import Generator


class TTLDeque[T]:
    """Add items to the beginning of the list and removes items when TTL expires."""

    def __init__(self, ttl: int = 5) -> None:
        """Initialize the deque."""
        self._ttl = timedelta(minutes=ttl)
        self._deque: deque[tuple[datetime, T]] = deque()

    def add(self, item: T, time: datetime | None = None) -> None:
        """Add an item."""
        self._deque.appendleft((time or dt_util.now(), item))
        self._prune()

    def _prune(self) -> None:
        """Remove expired items."""
        now = dt_util.now()
        while self._deque and now - self._deque[-1][0] >= self._ttl:
            self._deque.pop()

    def items(self) -> Generator[T]:
        """Return the items."""
        self._prune()
        for _, item in self._deque:
            yield item

    def changed(self) -> datetime | None:
        """Return the timestamp of the 1st (most recent) item."""
        self._prune()
        return self._deque[0][0] if self._deque else None
