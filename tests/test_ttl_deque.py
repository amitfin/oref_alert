"""Test for the queue with TTL implementation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from custom_components.oref_alert.ttl_deque import TTLDeque

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory


def test_deque(freezer: FrozenDateTimeFactory) -> None:
    """Test deque class."""
    deque = TTLDeque(2)
    assert deque.changed() is None
    deque.add({1: 1})
    assert deque.items() == [{1: 1}]
    now = datetime.now().timestamp()  # noqa: DTZ005
    changed = deque.changed()
    assert changed
    assert changed.timestamp() == now
    freezer.tick(timedelta(minutes=1))
    deque.add({2: 2})
    changed = deque.changed()
    assert changed
    assert changed.timestamp() == (now + 60)
    assert deque.items() == [{2: 2}, {1: 1}]
    freezer.tick(timedelta(minutes=1))
    assert deque.items() == [{2: 2}]
    freezer.tick(timedelta(minutes=1))
    assert not len(deque.items())
