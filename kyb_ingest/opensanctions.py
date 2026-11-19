"""Local matcher over OpenSanctions "targets.simple.csv" exports (e.g. gb_fcdo_sanctions, peps). Works offline on
the file; blocking by name tokens keeps it fast. The CSV columns used (id, schema, name, aliases, countries,
identifiers, birth_date, dataset, first_seen, last_seen) are tolerated if missing. Licence: check
opensanctions.org/licensing before redistribution or business use. The FCDO list is designations only: PEP
coverage needs a separate PEP dataset, loaded as its own SanctionsIndex."""
from __future__ import annotations
import csv, re
from collections import defaultdict
from .matching import Candidate, corroborate, name_score, normalise_name

_PERSON = {"Person"}


def _split(v): return [x.strip() for x in re.split(r"[;|]", v or "") if x.strip()]


class SanctionsIndex:
    def __init__(self, records, label):
        self.label, self.records, self.post = label, records, defaultdict(set)
        for i, r in enumerate(records):
            for nm in r["names"]:
                for t in normalise_name(nm, r["kind"]).split():
                    if len(t) >= 3: self.post[t].add(i)

    @classmethod
    def from_csv(cls, path, label):
        recs = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                kind = "person" if row.get("schema") in _PERSON else "company"
                recs.append(dict(
                    id=row.get("id", ""), kind=kind, names=[row.get("name", "")] + _split(row.get("aliases")),
                    countries=set(_split(row.get("countries"))), identifiers=set(_split(row.get("identifiers"))),
                    birth_years={int(m) for m in re.findall(r"\b(\d{4})\b", row.get("birth_date", "") or "")},
                    first_seen=row.get("first_seen"), last_seen=row.get("last_seen"), dataset=row.get("dataset")))
        return cls(recs, label)

    def match(self, name, kind="company", country=None, company_number=None, birth_year=None, threshold=0.88):
        q = dict(name=name, country=country, company_number=company_number, birth_year=birth_year)
        pool = set()
        for t in normalise_name(name, kind).split():
            pool |= self.post.get(t, set())
        out = []
        for i in pool:
            r = self.records[i]
            if r["kind"] != kind: continue
            best = max(((name_score(name, n, kind), n) for n in r["names"] if n), default=(0, ""))
            if best[0] >= threshold:
                c = Candidate(self.label, r["id"], best[1], round(best[0], 3),
                              evidence=dict(countries=sorted(r["countries"]), dataset=r["dataset"], last_seen=r["last_seen"]))
                out.append(corroborate(c, q, kind, r))
        return sorted(out, key=lambda c: (c.status != "corroborated", -c.score))


def flag_from_candidates(cands, unresolved="unknown"):
    """(flag, status): corroborated -> (1,'corroborated'); only candidates -> per `unresolved` policy
    ('unknown' -> None, 'positive' -> 1, 'negative' -> 0) with status 'unresolved_candidate'; none -> (0,'no_match')."""
    if any(c.status == "corroborated" for c in cands): return 1, "corroborated"
    if cands: return {"unknown": None, "positive": 1, "negative": 0}[unresolved], "unresolved_candidate"
    return 0, "no_match"
