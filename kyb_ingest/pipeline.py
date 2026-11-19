"""Assemble one feature row per company in the project's schema, keeping unknowns as None and recording evidence.
Network clients are injected; any may be None (that feature then stays unknown rather than defaulting to 0)."""
from __future__ import annotations
from datetime import date
from . import companies_house as ch
from .opensanctions import flag_from_candidates


def build_feature_row(company_number, as_of: date, house: "ch.CompaniesHouse", sanctions=None, peps=None, gdelt=None,
                      policy=None, gleif=None, unresolved="unknown", lookback_days=365):
    prof = house.profile(company_number)
    if prof is None: return dict(company_id=company_number, as_of_date=as_of.isoformat(), found=False)
    officers, filings, pscs = house.officers(company_number), house.filing_history(company_number), house.pscs(company_number)
    name = prof.get("company_name", "")
    row = dict(company_id=company_number, as_of_date=as_of.isoformat(), found=True, company_name=name,
               company_age_years=ch.company_age_years(prof, as_of), late_filings=ch.late_filings(prof, filings, as_of),
               officer_changes=ch.officer_changes(officers, as_of, lookback_days), industry=ch.industry(prof),
               company_status=prof.get("company_status"))
    countries = ch.countries_from_network(officers, pscs)
    if policy is not None:
        row["jurisdiction_flag"], row["jurisdiction_lists"] = policy.flag(countries, as_of)
    else:
        row["jurisdiction_flag"], row["jurisdiction_lists"] = None, []
    # entity + network screening: company, officers, individual PSCs, corporate PSCs
    people = [(o["name"], o.get("date_of_birth", {}).get("year"), o.get("country_of_residence") or o.get("nationality"))
              for o in officers or [] if o.get("name")]
    people += [(p["name"], (p.get("date_of_birth") or {}).get("year"), p.get("country_of_residence") or p.get("nationality"))
               for p in pscs or [] if p.get("name") and "corporate" not in p.get("kind", "")]
    corp_psc = [(p["name"], (p.get("identification") or {}).get("registration_number"), (p.get("identification") or {}).get("country_registered"))
                for p in pscs or [] if "corporate" in p.get("kind", "") and p.get("name")]
    for label, index in (("sanctions", sanctions), ("pep", peps)):
        if index is None:
            row[f"{'sanctions_proximity' if label == 'sanctions' else 'pep'}_flag"] = None
            row[f"{label}_status"] = "source_not_loaded"; row[f"{label}_hits"] = []; continue
        cands = []
        if label == "sanctions":
            cands += index.match(name, "company", country="United Kingdom", company_number=company_number)
            for n, num, cty in corp_psc: cands += index.match(n, "company", country=cty, company_number=num)
        for n, yr, cty in people: cands += index.match(n, "person", country=cty, birth_year=yr)
        flag, status = flag_from_candidates(cands, unresolved)
        row[f"{'sanctions_proximity' if label == 'sanctions' else 'pep'}_flag"] = flag
        row[f"{label}_status"] = status
        row[f"{label}_hits"] = [(c.entity_id, c.matched_name, c.score, c.status) for c in cands[:5]]
    if gdelt is not None:
        am = gdelt.adverse_media(name)
        row.update(am if am else dict(adverse_media_count=None))
    else:
        row["adverse_media_count"] = None
    if gleif is not None:
        recs = [r for r in gleif.search_by_name(name) if r.get("registered_as") == company_number]
        row["lei"] = recs[0]["lei"] if recs else None
    return row
