"""Companies House Public Data API client + feature builders (UK registry; authoritative for company facts).
Endpoint paths and the 600-requests/5-minutes limit are from memory and were NOT verified in this session
(docs host was unreachable) - confirm at https://developer.company-information.service.gov.uk before live use.
Auth: API key as the HTTP basic-auth username with an empty password. Key is read from COMPANIES_HOUSE_API_KEY."""
from __future__ import annotations
import os, calendar
from datetime import date, datetime
from .http import RateLimiter, make_getter

BASE = "https://api.company-information.service.gov.uk"


def _d(s):  # 'YYYY-MM-DD' -> date | None
    try: return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError): return None


def add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12); y += d.year
    return date(y, mo + 1, min(d.day, calendar.monthrange(y, mo + 1)[1]))


class CompaniesHouse:
    def __init__(self, api_key: str | None = None, get=None):
        key = api_key or os.environ.get("COMPANIES_HOUSE_API_KEY")
        if get is None:
            if not key: raise RuntimeError("Set COMPANIES_HOUSE_API_KEY or pass get=")
            get = make_getter(auth=(key, ""), limiter=RateLimiter(600, 300))
        self.get = get

    def profile(self, n): return self.get(f"{BASE}/company/{n}")
    def insolvency(self, n): return self.get(f"{BASE}/company/{n}/insolvency")
    def charges(self, n): return self.get(f"{BASE}/company/{n}/charges")

    def _paged(self, path, extra=None):
        items, start = [], 0
        while True:
            page = self.get(f"{BASE}{path}", {"items_per_page": 100, "start_index": start, **(extra or {})})
            if not page: break
            got = page.get("items", []); items += got; start += len(got)
            if not got or start >= page.get("total_results", 0): break
        return items

    def officers(self, n): return self._paged(f"/company/{n}/officers")
    def filing_history(self, n, category="accounts"): return self._paged(f"/company/{n}/filing-history", {"category": category})
    def pscs(self, n): return self._paged(f"/company/{n}/persons-with-significant-control")


# ------------------------------------------------------------------ feature builders (pure functions)
def company_age_years(profile, as_of: date):
    c = _d((profile or {}).get("date_of_creation"))
    return None if c is None else round((as_of - c).days / 365.25, 2)


def industry(profile):
    """First SIC code as TEXT (keeps leading zeros); None if absent."""
    sic = (profile or {}).get("sic_codes") or []
    return str(sic[0]) if sic else None


def officer_changes(officers, as_of: date, lookback_days=365):
    """Appointments + resignations inside the lookback window. None if no officer data was retrieved."""
    if officers is None: return None
    n = 0
    for o in officers:
        for k in ("appointed_on", "resigned_on"):
            d = _d(o.get(k))
            if d and 0 <= (as_of - d).days <= lookback_days: n += 1
    return n


def late_filings(profile, filings, as_of: date, lookback_years=3):
    """Accounts filed after their statutory deadline inside the lookback window, plus 1 if accounts are overdue now.
    Deadline = period end + 9 months (private) / 6 months (public); the very first accounts get at least
    incorporation + 21 months. Assumptions: made_up_date comes from filing description_values; extended-deadline
    cases (e.g. shortened accounting period) are not modelled, so treat the result as an estimate."""
    if filings is None: return None
    pub = (profile or {}).get("type") in ("plc", "old-public-company")
    months = 6 if pub else 9; created = _d((profile or {}).get("date_of_creation"))
    rows = []
    for f in filings:
        if f.get("type") != "AA": continue
        filed, made_up = _d(f.get("date")), _d((f.get("description_values") or {}).get("made_up_date"))
        if filed and made_up: rows.append((made_up, filed))
    rows.sort(); cutoff = date(as_of.year - lookback_years, as_of.month, min(as_of.day, 28)); n = 0
    for i, (made_up, filed) in enumerate(rows):
        due = add_months(made_up, months)
        if i == 0 and created: due = max(due, add_months(created, 21))
        if filed > due and cutoff <= filed <= as_of: n += 1
    if ((profile or {}).get("accounts") or {}).get("overdue"): n += 1
    return n


def countries_from_network(officers, pscs):
    """Country strings attached to officers/PSCs (residence, nationality, corporate PSC registration country)."""
    out = set()
    for p in list(officers or []) + list(pscs or []):
        for v in (p.get("country_of_residence"), p.get("nationality"),
                  (p.get("identification") or {}).get("country_registered")):
            if v: out.add(v)
    return out
