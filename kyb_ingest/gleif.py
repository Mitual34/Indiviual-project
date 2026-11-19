"""GLEIF LEI API (free, open data): legal-entity identity and parent relationships (ownership across borders).
Endpoint shape from memory, UNVERIFIED in this session. UK entities often carry their Companies House number in
`registeredAs`, which gives an identifier-level corroboration for matches."""
from __future__ import annotations
BASE = "https://api.gleif.org/api/v1"


class GLEIF:
    def __init__(self, get=None):
        if get is None:
            from .http import make_getter
            get = make_getter()
        self.get = get

    @staticmethod
    def _rec(d):
        a, e = d.get("attributes", {}), d.get("attributes", {}).get("entity", {})
        return dict(lei=a.get("lei") or d.get("id"), name=(e.get("legalName") or {}).get("name"),
                    jurisdiction=e.get("jurisdiction"), registered_as=e.get("registeredAs"), status=e.get("status"))

    def search_by_name(self, name, size=5):
        r = self.get(f"{BASE}/lei-records", {"filter[entity.legalName]": name, "page[size]": size})
        return [self._rec(d) for d in (r or {}).get("data", [])]

    def parents(self, lei):
        out = {}
        for rel in ("direct-parent", "ultimate-parent"):
            r = self.get(f"{BASE}/lei-records/{lei}/{rel}")
            out[rel] = self._rec(r["data"]) if r and r.get("data") else None
        return out
