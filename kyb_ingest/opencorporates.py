"""OpenCorporates client (cross-jurisdiction company records). Endpoint shape from memory, UNVERIFIED in this session.
Access/licensing: API use beyond the free tier needs a token and may need a paid or public-benefit licence - check
opencorporates.com/info/api before relying on it. Token from OPENCORPORATES_API_TOKEN."""
from __future__ import annotations
import os
BASE = "https://api.opencorporates.com/v0.4"


class OpenCorporates:
    def __init__(self, api_token=None, get=None):
        self.token = api_token or os.environ.get("OPENCORPORATES_API_TOKEN")
        if get is None:
            from .http import make_getter, RateLimiter
            get = make_getter(limiter=RateLimiter(50, 60))
        self.get = get

    def _p(self, extra): return {**extra, **({"api_token": self.token} if self.token else {})}

    def search(self, name, jurisdiction_code=None):
        r = self.get(f"{BASE}/companies/search", self._p({"q": name, **({"jurisdiction_code": jurisdiction_code} if jurisdiction_code else {})}))
        return [c["company"] for c in ((r or {}).get("results") or {}).get("companies", [])]

    def company(self, jurisdiction_code, number):
        r = self.get(f"{BASE}/companies/{jurisdiction_code}/{number}", self._p({}))
        return ((r or {}).get("results") or {}).get("company")
