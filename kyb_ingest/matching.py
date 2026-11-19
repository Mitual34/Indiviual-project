"""Entity resolution helpers. Principle from the project data guide: a name hit is only a CANDIDATE; it becomes a
flag only when corroborated by an independent attribute (identifier, birth year, country). Unresolved candidates are
kept as unknown, never silently turned into 0 or 1."""
from __future__ import annotations
import re, unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

LEGAL_SUFFIXES = {"ltd", "limited", "plc", "llp", "lp", "llc", "inc", "incorporated", "corp", "corporation", "co", "company",
                  "gmbh", "ag", "sa", "bv", "nv", "oy", "ab", "as", "srl", "spa", "pjsc", "ojsc", "jsc", "the", "and"}
TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "dame", "lord", "lady", "mx"}


def normalise_name(s: str, kind: str = "company") -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().casefold()
    s = re.sub(r"[^a-z0-9 ]+", " ", s.replace("&", " and "))
    drop = LEGAL_SUFFIXES if kind == "company" else TITLES
    return " ".join(t for t in s.split() if t not in drop)


def name_score(a: str, b: str, kind: str = "company") -> float:
    """max(sequence similarity, token-set Jaccard) on normalised names, in [0,1]. Person names are compared
    order-insensitively because registries write 'SURNAME, Forename'."""
    na, nb = normalise_name(a, kind), normalise_name(b, kind)
    if not na or not nb: return 0.0
    ta, tb = set(na.split()), set(nb.split()); jac = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, " ".join(sorted(ta)) if kind == "person" else na,
                          " ".join(sorted(tb)) if kind == "person" else nb).ratio()
    return max(seq, jac)


@dataclass
class Candidate:
    source: str            # e.g. 'uk_fcdo_sanctions', 'peps'
    entity_id: str
    matched_name: str
    score: float
    status: str = "candidate"          # 'candidate' | 'corroborated'
    reasons: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def corroborate(c: Candidate, query: dict, kind: str, record: dict) -> Candidate:
    """query: {'name', 'country'?, 'company_number'?, 'birth_year'?}. record: the reference-list entry
    ({'identifiers': set, 'countries': set, 'birth_years': set}). Rules:
      * identifier match (company number)                      -> corroborated
      * company: normalised-name equality AND country match    -> corroborated
      * person : name score >= 0.95 AND birth-year match       -> corroborated
    Anything else stays a candidate."""
    ids = {i.casefold() for i in record.get("identifiers", ())}
    if query.get("company_number") and str(query["company_number"]).casefold() in ids:
        c.reasons.append("identifier match")
    if kind == "company":
        exact = normalise_name(query["name"]) == normalise_name(c.matched_name)
        cty = bool(query.get("country")) and query["country"].casefold() in {x.casefold() for x in record.get("countries", ())}
        if exact and cty: c.reasons.append("exact name + country")
    else:
        by = query.get("birth_year")
        if c.score >= 0.95 and by and int(by) in record.get("birth_years", ()): c.reasons.append("name + birth year")
    if c.reasons: c.status = "corroborated"
    return c
