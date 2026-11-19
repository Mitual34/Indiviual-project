"""Registry of data sources for UK KYC/KYB/AML screening. `status`: implemented (code here) | planned (worth adding) |
manual (analyst tool, not a pipeline source) | deferred/excluded (with reason). `verified`: whether access terms and
endpoints were checked live in this project (none were: the network blocked the docs hosts). Check licences first."""
import csv, sys

# (name, layer, status, maps_to, access_note)
SOURCES = [
 ("Companies House REST API", "registry", "implemented", "age, status, SIC, late filings, officer changes, PSCs", "free API key; ~600 req/5 min (unverified)"),
 ("Companies House bulk (BasicCompanyData, PSC snapshot)", "registry", "planned", "backtest/universe building, ownership", "free download; single snapshot date"),
 ("Companies House: disqualified officers, insolvency, charges", "registry", "planned", "director and distress risk", "free API (insolvency and charges paths are in the client)"),
 ("Companies House Register of Overseas Entities", "ownership", "planned", "overseas owners of UK property", "free"),
 ("OpenSanctions: UK FCDO sanctions list", "sanctions", "implemented", "sanctions_proximity_flag", "free non-commercial; business use needs licence"),
 ("OpenSanctions: PEP dataset", "pep", "implemented", "pep_flag", "same licence note; FCDO list has no PEPs"),
 ("UK Sanctions List (FCDO) / OFSI list direct", "sanctions", "planned", "primary-source cross-check of OpenSanctions mirror", "government publication; confirm which list is current"),
 ("GDELT DOC 2.0 API", "adverse media", "implemented", "adverse_media_count", "free; ~3 month window (unverified); BigQuery GKG for history"),
 ("OpenCorporates", "registry (global)", "implemented", "foreign registrations, jurisdiction context", "token; restricted free use"),
 ("GLEIF LEI API", "ownership (global)", "implemented", "LEI, direct/ultimate parent", "free open data"),
 ("The Gazette (insolvency and winding-up notices)", "distress", "planned", "insolvency events", "free API/feeds"),
 ("FCA Financial Services Register + FCA warning list", "regulatory", "planned", "authorisation status, clone/unauthorised firms", "free API key"),
 ("HMRC VAT number check", "tax identity", "planned", "VAT registration validity", "free, needs HMRC developer app"),
 ("HM Land Registry CCOD/OCOD", "property ownership", "planned", "companies/overseas companies owning UK property", "free dataset, licence terms"),
 ("Charity Commission register", "registry", "planned", "charity/NPO customers", "free"),
 ("UK high-risk third countries (MLR 2017 Sch 3ZA) + FATF lists", "jurisdiction policy", "planned", "jurisdiction_flag (policy, not data)", "official publications; see policy/README.md"),
 ("SecurityTrails", "infrastructure", "manual", "domain age/shared hosting for shell-company triage", "small free tier"),
 ("Maltego CE", "analyst tool", "manual", "link analysis on flagged cases", "not a pipeline source"),
 ("SpiderFoot", "analyst tool", "manual", "automated OSINT on flagged cases", "not a pipeline source"),
 ("Social Searcher / Reddit search", "social", "deferred", "noisy; individuals' data", "UK GDPR review first"),
 ("Sentinel Hub / Global Fishing Watch / OpenSky", "geospatial/maritime/aviation", "excluded", "only sector-specific site verification", "poor fit for UK company screening at scale"),
]
COLS = ["source", "layer", "status", "maps_to", "access_note"]


def write_csv(path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(COLS + ["verified_live"]); [w.writerow(list(r) + ["no"]) for r in SOURCES]


if __name__ == "__main__":
    write_csv(sys.argv[1] if len(sys.argv) > 1 else "source_registry.csv")
