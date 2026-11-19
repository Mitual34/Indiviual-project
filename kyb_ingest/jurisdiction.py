"""Dated jurisdiction-risk policy lookup (see policy/README.md). Country names are matched after normalisation."""
from __future__ import annotations
import csv
from datetime import date, datetime
from .matching import normalise_name


class JurisdictionPolicy:
    def __init__(self, rows): self.rows = rows

    @classmethod
    def load(cls, path):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                rows = [dict(country=normalise_name(r["country"], "person"), list=r["list_name"],
                             start=datetime.strptime(r["effective_from"], "%Y-%m-%d").date(),
                             end=datetime.strptime(r["effective_to"], "%Y-%m-%d").date() if r.get("effective_to") else None)
                        for r in csv.DictReader(f)]
        except FileNotFoundError:
            return None
        return cls(rows) if rows else None

    def flag(self, countries, as_of: date):
        """1 if any country was on a list at as_of; 0 if countries known and none listed; None if no countries."""
        cs = {normalise_name(c, "person") for c in countries or ()}
        if not cs: return None, []
        hit = [r["list"] for r in self.rows if r["country"] in cs and r["start"] <= as_of and (r["end"] is None or as_of <= r["end"])]
        return (1 if hit else 0), sorted(set(hit))
