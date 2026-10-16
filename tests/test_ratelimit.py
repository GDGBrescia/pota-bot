from pota_bot.ratelimit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_allows_up_to_limit_then_blocks():
    clock = FakeClock()
    limiter = RateLimiter(max_per_hour=2, clock=clock)
    assert limiter.allow("anna")
    assert limiter.allow("anna")
    assert not limiter.allow("anna")


def test_limit_is_per_person():
    limiter = RateLimiter(max_per_hour=1, clock=FakeClock())
    assert limiter.allow("anna")
    assert limiter.allow("bruno")


def test_window_slides_after_one_hour():
    clock = FakeClock()
    limiter = RateLimiter(max_per_hour=1, clock=clock)
    assert limiter.allow("anna")
    clock.now = 3599
    assert not limiter.allow("anna")
    clock.now = 3600
    assert limiter.allow("anna")
