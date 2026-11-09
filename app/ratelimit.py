"""Ограничение частоты: не больше limit событий за окно window на один ключ.

Хранится в памяти процесса: при одном процессе uvicorn этого достаточно.
"""
import math
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Callable


class RateLimiter:
    def __init__(self, limit: int, window: timedelta,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.limit = limit
        self.window = window
        self.now = now
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        """Сколько секунд ждать до следующей попытки; 0 — можно сейчас."""
        with self._lock:
            hits = self._fresh(key)
            if len(hits) < self.limit:
                return 0
            wait = hits[0] + self.window - self.now()
            return max(1, math.ceil(wait.total_seconds()))

    def hit(self, key: str) -> None:
        with self._lock:
            self._fresh(key).append(self.now())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _fresh(self, key: str) -> deque[datetime]:
        hits = self._hits[key]
        border = self.now() - self.window
        while hits and hits[0] <= border:
            hits.popleft()
        return hits
