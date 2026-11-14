from datetime import datetime, timedelta, timezone

from app.ratelimit import RateLimiter


class Clock:
    def __init__(self):
        self.now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def test_blocks_after_limit_until_window_passes():
    clock = Clock()
    limiter = RateLimiter(limit=5, window=timedelta(minutes=5), now=clock)

    for _ in range(5):
        assert limiter.retry_after("anna") == 0
        limiter.hit("anna")

    assert limiter.retry_after("anna") == 300
    clock.now += timedelta(minutes=2)
    assert limiter.retry_after("anna") == 180
    clock.now += timedelta(minutes=3, seconds=1)
    assert limiter.retry_after("anna") == 0


def test_keys_are_independent_and_reset_clears():
    limiter = RateLimiter(limit=1, window=timedelta(minutes=5), now=Clock())
    limiter.hit("anna")

    assert limiter.retry_after("anna") > 0
    assert limiter.retry_after("boris") == 0
    limiter.reset("anna")
    assert limiter.retry_after("anna") == 0


def test_keys_without_fresh_hits_are_forgotten():
    clock = Clock()
    limiter = RateLimiter(limit=5, window=timedelta(minutes=5), now=clock)
    limiter.hit("anna")
    clock.now += timedelta(minutes=5, seconds=1)

    assert limiter.retry_after("anna") == 0
    assert len(limiter) == 0


def test_stale_keys_nobody_asks_about_again_are_swept():
    clock = Clock()
    limiter = RateLimiter(limit=5, window=timedelta(minutes=5), now=clock)
    for i in range(100):
        limiter.hit(f"random-login-{i}")
    clock.now += timedelta(minutes=5, seconds=1)

    limiter.hit("anna")

    assert len(limiter) == 1
