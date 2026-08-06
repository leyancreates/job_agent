"""Thread-safe in-process TTL cache for public board responses."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Generic, Hashable, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float = 900, *, time_fn: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self._time_fn = time_fn
        self._values: dict[Hashable, tuple[float, T]] = {}
        self._key_locks: dict[Hashable, threading.Lock] = {}
        self._lock = threading.Lock()

    def _fresh_value(self, key: Hashable) -> T | None:
        with self._lock:
            item = self._values.get(key)
            if item and item[0] > self._time_fn():
                return item[1]
            if item:
                self._values.pop(key, None)
        return None

    def get_or_load(self, key: Hashable, loader: Callable[[], T]) -> T:
        cached = self._fresh_value(key)
        if cached is not None:
            return cached

        with self._lock:
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:
            cached = self._fresh_value(key)
            if cached is not None:
                return cached
            value = loader()
            with self._lock:
                self._values[key] = (self._time_fn() + self.ttl_seconds, value)
            return value

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


PUBLIC_BOARD_CACHE: TTLCache = TTLCache(ttl_seconds=900)

