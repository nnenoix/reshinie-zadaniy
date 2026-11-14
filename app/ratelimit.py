"""Ограничение частоты: не больше limit событий за окно window на один ключ.

Хранится в памяти процесса: при одном процессе uvicorn этого достаточно.
Ключ без свежих событий удаляется, а раз в окно удаляются все такие ключи —
поэтому случайные логины, с которыми больше не приходят, память не копят.
"""
import math
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable


class RateLimiter:
    def __init__(self, limit: int, window: timedelta,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.limit = limit
        self.window = window
        self.now = now
        self._hits: dict[str, deque[datetime]] = {}
        self._swept_at = now()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        """Сколько ключей сейчас в памяти."""
        with self._lock:
            return len(self._hits)

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
            self._sweep()
            self._hits.setdefault(key, deque()).append(self.now())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _fresh(self, key: str) -> deque[datetime]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        border = self.now() - self.window
        while hits and hits[0] <= border:
            hits.popleft()
        if not hits:
            del self._hits[key]
        return hits

    def _sweep(self) -> None:
        if self.now() - self._swept_at < self.window:
            return
        self._swept_at = self.now()
        for key in list(self._hits):
            self._fresh(key)
