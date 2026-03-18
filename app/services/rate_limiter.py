"""Async token bucket rate limiter — shared across all Etherscan V2 API calls."""
import asyncio
import time


class AsyncRateLimiter:
    """
    Token bucket rate limiter for async code.

    Allows up to `burst` calls immediately, then refills at `rate` tokens/second.
    Thread-safe via asyncio.Lock (single event loop assumed — matches single-worker deployment).
    """

    def __init__(self, rate: float, burst: int):
        self._rate = rate        # tokens added per second
        self._burst = float(burst)  # max tokens
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a token is available, then consume one."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._last_refill = now
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)

            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# Singleton shared across ALL Etherscan V2 calls (single API key = single rate limit).
# Set slightly below 5/s to avoid hitting the boundary.
etherscan_limiter = AsyncRateLimiter(rate=4.0, burst=4)
