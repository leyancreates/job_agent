"""Thread-safe TTL cache for resume match results."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class MatchCache(Generic[T]):
    def __init__(
        self,
        ttl_seconds: float = 21_600,
        *,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._time_fn = time_fn
        self._values: dict[str, tuple[float, T]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        with self._lock:
            item = self._values.get(key)
            if item and item[0] > self._time_fn():
                return item[1]
            if item:
                self._values.pop(key, None)
        return None

    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._values[key] = (self._time_fn() + self.ttl_seconds, value)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
