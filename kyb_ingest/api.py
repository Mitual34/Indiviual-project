"""JSON API behind the console. Pure functions over a context, so they are testable without sockets.
The Companies House key lives only in the server process; the browser never sees it."""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs, urlparse
from .pipeline import build_feature_row

NUM = re.compile(r"^[A-Za-z0-9]{6,8}$")


@dataclass
class Context:
    house: object = None
    sanctions: object = None
    peps: object = None
    policy: object = None
    geocode: object = None          # callable(postcode) -> {"lat","lon"} | None
    mode: str = "off"               # 'live' | 'fake' | 'off'


class CachedHouse:
    """Memoise the client's calls for one request so the pipeline and the payload builder share one fetch."""
    def __init__(self, house): self._h, self._c = house, {}
    def __getattr__(self, name):
        f = getattr(self._h, name)
        def w(*a, **k):
            key = (name, a, tuple(sorted(k.items())))
            if key not in self._c: self._c[key] = f(*a, **k)
            return self._c[key]
        return w


def status(ctx):
    return dict(mode=ctx.mode, live=ctx.house is not None, sanctions=ctx.sanctions is not None, peps=ctx.peps is not None,
                policy=ctx.policy is not None, geocode=ctx.geocode is not None)


def search(ctx, q):
    if ctx.house is None: return 503, {"error": "Live lookup is off. Restart the server with an API key."}
    q = (q or "").strip()
    if len(q) < 2 or len(q) > 100: return 400, {"error": "Enter 2 to 100 characters."}
    items = ctx.house.search(q, 10)
    return 200, {"items": [dict(number=i.get("company_number"), name=i.get("title"), status=i.get("company_status"),
                                created=i.get("date_of_creation"), address=i.get("address_snippet")) for i in items]}


def _officer(o):
    dob = o.get("date_of_birth") or {}
    return dict(name=o.get("name"), role=o.get("officer_role"), appointed=o.get("appointed_on"), resigned=o.get("resigned_on"),
                residence=o.get("country_of_residence"), nationality=o.get("nationality"), birth_year=dob.get("year"))


def _psc(p):
    return dict(name=p.get("name"), kind=(p.get("kind") or "").replace("-person-with-significant-control", "").replace("-", " "),
                control=[c.replace("-", " ") for c in p.get("natures_of_control", [])],
                country=(p.get("identification") or {}).get("country_registered") or p.get("country_of_residence"))


def company(ctx, number, as_of=None):
    if ctx.house is None: return 503, {"error": "Live lookup is off. Restart the server with an API key."}
    if not NUM.match(number or ""): return 400, {"error": "Company numbers are 6 to 8 letters or digits."}
    number = number.upper().zfill(8) if number.isdigit() else number.upper()
    h = CachedHouse(ctx.house)
    row = build_feature_row(number, as_of or date.today(), h, ctx.sanctions, ctx.peps, None, ctx.policy)
    if not row.get("found"): return 404, {"error": f"No company {number} found."}
    prof, addr = h.profile(number), (h.profile(number).get("registered_office_address") or {})
    geo = ctx.geocode(addr.get("postal_code")) if ctx.geocode and addr.get("postal_code") else None
    return 200, dict(row=row, profile=dict(name=prof.get("company_name"), number=number, status=prof.get("company_status"), type=prof.get("type"),
                     created=prof.get("date_of_creation"), sic=prof.get("sic_codes"), accounts_overdue=(prof.get("accounts") or {}).get("overdue"),
                     office=", ".join(x for x in (addr.get("address_line_1"), addr.get("locality"), addr.get("postal_code")) if x)),
                     officers=[_officer(o) for o in h.officers(number) or []], pscs=[_psc(p) for p in h.pscs(number) or []], geo=geo, mode=ctx.mode)


def handle(ctx, url):
    """url like '/api/company/00445790' or '/api/search?q=acme' -> (http_status, json_dict)."""
    u = urlparse(url); parts = [p for p in u.path.split("/") if p]
    try:
        if parts[:2] == ["api", "status"]: return 200, status(ctx)
        if parts[:2] == ["api", "search"]: return search(ctx, parse_qs(u.query).get("q", [""])[0])
        if parts[:2] == ["api", "company"] and len(parts) == 3: return company(ctx, parts[2])
    except Exception as e:  # map client/network failures to readable errors, never leak the key
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (401, 403): return 502, {"error": "Companies House rejected the API key."}
        if code == 429: return 429, {"error": "Companies House rate limit reached. Wait a minute and retry."}
        return 502, {"error": "Companies House request failed: " + type(e).__name__}
    return 404, {"error": "Unknown endpoint."}
