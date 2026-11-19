"""Tiny HTTP layer: client-side rate limiting, retry on 429/5xx, and an injectable `get` so that every client can be
tested offline. A `get` is any callable  get(url, params=None) -> dict | None  (None means HTTP 404)."""
from __future__ import annotations
import time
from collections import deque


class RateLimiter:
    """Allow at most `max_calls` per `period` seconds (sliding window). Clock and sleep are injectable for tests."""

    def __init__(self, max_calls: int, period: float, clock=time.monotonic, sleep=time.sleep):
        self.max_calls, self.period, self.clock, self.sleep = max_calls, period, clock, sleep
        self.calls: deque[float] = deque()

    def wait(self):
        now = self.clock()
        while self.calls and now - self.calls[0] >= self.period: self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            self.sleep(self.period - (now - self.calls[0])); now = self.clock()
            while self.calls and now - self.calls[0] >= self.period: self.calls.popleft()
        self.calls.append(self.clock())


def make_getter(auth=None, headers=None, limiter: RateLimiter | None = None, retries=3, timeout=30, session=None):
    import requests
    s = session or requests.Session()

    def get(url, params=None):
        for attempt in range(retries + 1):
            if limiter: limiter.wait()
            r = s.get(url, params=params, auth=auth, headers=headers, timeout=timeout)
            if r.status_code == 404: return None
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(float(r.headers.get("Retry-After", 2 ** attempt))); continue
            r.raise_for_status(); return r.json()
    return get
