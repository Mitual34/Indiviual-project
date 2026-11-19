"""Run on YOUR machine: checks the Companies House client against the live API and prints structure only.
    export COMPANIES_HOUSE_API_KEY=<your key>      (PowerShell: $env:COMPANIES_HOUSE_API_KEY="<your key>")
    python -m kyb_ingest.live_check 00445790
The key is read from the environment and is never written anywhere by this script."""
import sys
from datetime import date
from . import companies_house as ch


def main(number="00445790"):
    h = ch.CompaniesHouse(); today = date.today()
    p = h.profile(number)
    if p is None: print("company not found"); return
    print("profile keys:", sorted(p)); print({k: p.get(k) for k in ("company_status", "type", "date_of_creation", "sic_codes")})
    o, f, s = h.officers(number), h.filing_history(number), h.pscs(number)
    print("officers:", len(o), "| keys:", sorted(o[0]) if o else None)
    print("filings (accounts):", len(f), "| keys:", sorted(f[0]) if f else None)
    print("sample AA description_values:", [x.get("description_values") for x in f if x.get("type") == "AA"][:2])
    print("pscs:", len(s), "| kinds:", sorted({x.get("kind") for x in s}))
    print("features:", dict(age=ch.company_age_years(p, today), industry=ch.industry(p),
                            officer_changes=ch.officer_changes(o, today), late_filings=ch.late_filings(p, f, today)))


if __name__ == "__main__":
    main(*sys.argv[1:2])
