# kyb_ingest - UK KYC/KYB/AML ingestion and entity-matching skeleton

Builds one feature row per company in the project schema (`company_age_years, late_filings, officer_changes, industry,
company_status, jurisdiction_flag, pep_flag, sanctions_proximity_flag`) plus `adverse_media_count`, `lei` and evidence
columns. Unknowns stay `None`; a name-only hit is a *candidate* and only becomes a flag when corroborated.

| Module | Source | Status |
|---|---|---|
| `companies_house.py` | Companies House REST API | implemented, offline-tested |
| `opensanctions.py` | OpenSanctions `targets.simple.csv` (UK FCDO sanctions; PEP dataset loaded separately) | implemented, offline-tested |
| `gdelt.py` | GDELT DOC 2.0 (adverse media, recent window) | implemented, offline-tested |
| `opencorporates.py`, `gleif.py` | OpenCorporates, GLEIF LEI | implemented, response parsing only |
| `jurisdiction.py` + `policy/` | dated policy file YOU fill from official lists | implemented; file not shipped |
| `sources.py` / `source_registry.csv` | full UK landscape: planned, manual, deferred, excluded sources | registry only |

Run tests: `python -m pytest kyb_ingest/tests` (no network or keys needed).
Live use: set `COMPANIES_HOUSE_API_KEY` (and `OPENCORPORATES_API_TOKEN` if used); download OpenSanctions CSVs;
create `policy/high_risk_jurisdictions.csv` (see `policy/README.md`).

## Limits - read before relying on it
- **No endpoint was checked live.** The session's network blocked the docs hosts, so paths, rate limits and response
  shapes are from memory. Expect to adjust on first live call.
- `late_filings` is an estimate (statutory deadline rules only; extensions not modelled).
- GDELT DOC covers only a recent window (unverified, about 3 months), so it cannot back-test history.
- Jurisdiction flag matches country *names* from officers/PSCs, not ISO codes.
- Licences (OpenSanctions, OpenCorporates, SecurityTrails) must be checked before business use.
- Planned sources (Gazette, FCA Register, HMRC VAT, Land Registry, Charity Commission, ROE, disqualified officers,
  FATF/UK high-risk lists) are listed in `source_registry.csv` but have no code yet.
