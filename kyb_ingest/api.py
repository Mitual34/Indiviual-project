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
    fake: bool = False              # started with --fake: keep the fictional house unless a real key is saved
    oc_token: str | None = None
    key_source: str | None = None   # 'saved' | 'environment' | None
    errors: dict = None             # last problem per component, shown in Settings


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
    return dict(mode=ctx.mode, opencorporates=bool(ctx.oc_token), live=ctx.house is not None, sanctions=ctx.sanctions is not None, peps=ctx.peps is not None,
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
        if parts[:2] == ["api", "oc"]: return oc_search(ctx, parse_qs(u.query).get("q", [""])[0])
    except Exception as e:  # map client/network failures to readable errors, never leak the key
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (401, 403): return 502, {"error": "Companies House rejected the API key."}
        if code == 429: return 429, {"error": "Companies House rate limit reached. Wait a minute and retry."}
        return 502, {"error": "Companies House request failed: " + type(e).__name__}
    return 404, {"error": "Unknown endpoint."}


# ---------------------------------------------------------------- settings, connection test, other registries
import os
from .settings import mask


def rebuild(ctx, store):
    """(Re)create the live pieces from the settings store and environment. Errors are kept in ctx.errors, never raised."""
    from . import companies_house as ch, fake
    ctx.errors = {}; key, ctx.key_source = store.data.get("ch"), "saved" if store.data.get("ch") else None
    if not key and os.environ.get("COMPANIES_HOUSE_API_KEY"): key, ctx.key_source = os.environ["COMPANIES_HOUSE_API_KEY"].strip(), "environment"
    if key:
        try: ctx.house, ctx.mode = ch.CompaniesHouse(api_key=key), "live"
        except ImportError: ctx.house, ctx.mode = None, "off"; ctx.errors["companies_house"] = "The Python package 'requests' is not installed. Run: pip install requests"
        except Exception as e: ctx.house, ctx.mode = None, "off"; ctx.errors["companies_house"] = type(e).__name__
    elif ctx.fake: ctx.house, ctx.mode = fake.FakeHouse(), "fake"
    else: ctx.house, ctx.mode = None, "off"
    for name, k in (("sanctions", "sanctions_path"), ("peps", "peps_path")):
        setattr(ctx, name, None); path = store.data.get(k)
        if path:
            try:
                from .opensanctions import SanctionsIndex
                setattr(ctx, name, SanctionsIndex.from_csv(path, name))
            except Exception as e: ctx.errors[name] = f"Could not load {path}: {type(e).__name__}"
    ctx.policy = None
    if store.data.get("policy_path"):
        from .jurisdiction import JurisdictionPolicy
        ctx.policy = JurisdictionPolicy.load(store.data["policy_path"])
        if ctx.policy is None: ctx.errors["policy"] = "Policy file missing or has no rows."
    ctx.oc_token = store.data.get("oc")
    if ctx.mode == "fake": ctx.geocode = fake.fake_geocode
    elif ctx.mode == "live" and store.data.get("geocode", True):
        from .http import make_getter, RateLimiter
        get = make_getter(limiter=RateLimiter(30, 60))
        def geocode(pc):
            try:
                r = get("https://api.postcodes.io/postcodes/" + pc.replace(" ", ""))
                return {"lat": r["result"]["latitude"], "lon": r["result"]["longitude"]} if r and r.get("result") else None
            except Exception: return None
        ctx.geocode = geocode
    else: ctx.geocode = None


def settings_state(ctx, store):
    d = store.data
    return dict(mode=ctx.mode, remembered=store.persisted, store_path=str(store.path),
                companies_house=dict(set=bool(d.get("ch")) or ctx.key_source == "environment", hint=mask(d.get("ch")), source=ctx.key_source),
                opencorporates=dict(set=bool(d.get("oc")), hint=mask(d.get("oc"))),
                lists={k: dict(path=d.get(k + "_path", ""), loaded=getattr(ctx, k) is not None) for k in ("sanctions", "peps", "policy")},
                geocode=bool(d.get("geocode", True)), errors=ctx.errors or {})


def apply_settings(ctx, store, body):
    if not isinstance(body, dict): return 400, {"error": "Expected a JSON object."}
    patch = {}
    for field, k in (("companies_house_key", "ch"), ("opencorporates_token", "oc")):
        v = body.get(field)
        if v is not None:
            if not isinstance(v, str) or len(v) > 200 or any(c in v for c in "\r\n "): return 400, {"error": "That key has spaces or line breaks. Paste only the key."}
            patch[k] = v.strip()
    for field, k in (("sanctions_path", "sanctions_path"), ("peps_path", "peps_path"), ("policy_path", "policy_path")):
        v = body.get(field)
        if v is not None:
            if not isinstance(v, str) or len(v) > 500: return 400, {"error": "Invalid path."}
            v = v.strip().strip('"')
            if v and not v.lower().endswith(".csv"): return 400, {"error": "Reference lists must be .csv files."}
            if v and not os.path.isfile(v): return 400, {"error": f"File not found: {v}"}
            patch[k] = v
    if "geocode" in body: patch["geocode"] = bool(body["geocode"])
    store.update(**patch)
    if body.get("forget"): store.forget()
    elif "remember" in body:
        if body["remember"]: store.save()
        else:
            was = dict(store.data); store.forget(); store.data.update(was)
    rebuild(ctx, store)
    return 200, settings_state(ctx, store)


def test_connection(ctx):
    """One cheap authenticated call; returns a readable diagnosis."""
    if ctx.house is None:
        return 200, dict(ok=False, status=None, message=(ctx.errors or {}).get("companies_house") or "No Companies House key set. Paste it above and press Save.")
    if ctx.mode == "fake": return 200, dict(ok=True, status=200, message="Demo mode: no real request was made.")
    try:
        r = ctx.house.profile("00445790")
        return 200, dict(ok=r is not None, status=200 if r else 404, message="Connected. Companies House accepted the key." if r else "Key accepted but the test company was not found.")
    except ImportError:
        return 200, dict(ok=False, status=None, message="The Python package 'requests' is not installed. Run: pip install requests")
    except Exception as e:
        resp = getattr(e, "response", None); code = getattr(resp, "status_code", None); text = ""
        try: text = (resp.json() or {}).get("error", "")
        except Exception: pass
        hints = {400: "Companies House could not read the key. Paste only the key text, with no quotes or spaces.",
                 401: "Companies House rejected the key. Use a REST API key (not a stream key) from your registered application.",
                 403: "Access denied. If the key has a restricted-IP setting, this computer's address must be allowed.",
                 429: "Rate limit reached. Wait a few minutes."}
        if code: return 200, dict(ok=False, status=code, message=hints.get(code, "Companies House returned an error.") + (f" ({text})" if text else ""))
        return 200, dict(ok=False, status=None, message="Could not reach Companies House: " + type(e).__name__ + ". Check your internet connection or proxy.")


def oc_search(ctx, q):
    if not ctx.oc_token: return 503, {"error": "No OpenCorporates token set (Settings)."}
    q = (q or "").strip()
    if len(q) < 2 or len(q) > 100: return 400, {"error": "Enter 2 to 100 characters."}
    from .opencorporates import OpenCorporates
    items = OpenCorporates(api_token=ctx.oc_token).search(q)
    return 200, {"items": [dict(name=i.get("name"), number=i.get("company_number"), jurisdiction=i.get("jurisdiction_code"), status=i.get("current_status")) for i in items[:10]]}
