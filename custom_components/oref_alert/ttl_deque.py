"""Implementation of queue with TTL."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import homeassistant.util.dt as dt_util

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable


class TTLDeque[T]:
    """Keep items sorted from newest to oldest, and remove them when TTL expires."""

    def __init__(self, ttl: int = 5) -> None:
        """Initialize the deque."""
        self._ttl = timedelta(minutes=ttl)
        self._deque: deque[tuple[datetime, T]] = deque()

    def add(self, item: T, time: datetime | None = None) -> None:
        """Add an item."""
        time = time or dt_util.now()
        if self._deque and time < self._deque[0][0]:
            self.add_many([(item, time)])
            return
        self._deque.appendleft((time, item))
        self._prune()

    def add_many(self, items: Iterable[tuple[T, datetime]]) -> None:
        """Add items of any time, e.g. older than the existing ones."""
        if not (entries := [(time, item) for item, time in items]):
            return
        self._deque = deque(
            sorted(
                [*entries, *self._deque],
                key=lambda entry: entry[0],
                reverse=True,
            )
        )
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

    def __contains__(self, item: T) -> bool:
        """Check if the item exists."""
        self._prune()
        return any(item == check for _, check in self._deque)
