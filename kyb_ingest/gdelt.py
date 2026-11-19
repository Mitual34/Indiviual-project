"""GDELT adverse-media feature. Uses the DOC 2.0 API (free, no key). From memory and UNVERIFIED here: the DOC API only
searches roughly the most recent 3 months, so it suits live screening, not historical back-testing; for history use
the GDELT GKG tables in BigQuery (needs a GCP project). Name-only searches are noisy: results are re-filtered so the
company's name must appear in the article title, and only risk-term queries are issued."""
from __future__ import annotations
from .matching import normalise_name

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
RISK_TERMS = ["fraud", '"money laundering"', "sanctions", "bribery", "corruption", "fined", "investigation", "launder", "scandal"]


def build_query(company_name: str, terms=RISK_TERMS, english_only=True) -> str:
    q = f'"{company_name}" ({" OR ".join(terms)})'
    return q + (" sourcelang:english" if english_only else "")


def score_articles(articles, company_name):
    """Keep articles whose title contains every normalised token of the company name; return counts."""
    toks = normalise_name(company_name).split(); kept = []
    for a in articles or []:
        title = set(normalise_name(a.get("title", "")).split())
        if toks and all(t in title for t in toks): kept.append(a)
    return dict(adverse_media_count=len(kept), adverse_media_domains=len({a.get("domain") for a in kept if a.get("domain")}),
                adverse_media_examples=[a.get("url") for a in kept[:3]])


class GDELTDoc:
    def __init__(self, get=None):
        if get is None:
            from .http import make_getter, RateLimiter
            get = make_getter(limiter=RateLimiter(1, 5))  # be polite: ~1 request / 5 s
        self.get = get

    def adverse_media(self, company_name, timespan="3months", maxrecords=75):
        res = self.get(URL, {"query": build_query(company_name), "mode": "artlist", "format": "json",
                             "maxrecords": maxrecords, "timespan": timespan, "sort": "datedesc"})
        return score_articles((res or {}).get("articles", []), company_name) if res is not None else None
