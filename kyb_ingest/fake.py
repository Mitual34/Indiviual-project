"""A fictional Companies House stand-in for development and tests (no network). Company number 00000001 only."""
PROFILE = {"company_name": "ACME DEMO HOLDINGS LIMITED", "company_number": "00000001", "company_status": "active", "date_of_creation": "2018-03-01",
           "sic_codes": ["01110", "62020"], "type": "ltd", "accounts": {"overdue": False},
           "registered_office_address": {"address_line_1": "1 Demo Street", "locality": "Leeds", "postal_code": "LS1 1AA", "country": "England"}}
OFFICERS = [{"name": "DOE, Jane", "officer_role": "director", "appointed_on": "2025-01-10", "date_of_birth": {"year": 1970, "month": 5}, "country_of_residence": "Atlantis", "nationality": "Atlantean"},
            {"name": "ROE, Rich", "officer_role": "director", "appointed_on": "2015-01-01", "resigned_on": "2024-12-01", "country_of_residence": "United Kingdom"},
            {"name": "OLD, Ollie", "officer_role": "secretary", "appointed_on": "2010-01-01", "resigned_on": "2019-01-01"}]
FILINGS = [{"type": "AA", "date": "2021-01-15", "description_values": {"made_up_date": "2020-03-31"}},
           {"type": "AA", "date": "2023-01-20", "description_values": {"made_up_date": "2022-03-31"}},
           {"type": "AA", "date": "2023-11-01", "description_values": {"made_up_date": "2023-03-31"}},
           {"type": "AA", "date": "2025-02-01", "description_values": {"made_up_date": "2024-03-31"}}]
PSCS = [{"name": "Shell Parent Ltd", "kind": "corporate-entity-person-with-significant-control", "natures_of_control": ["ownership-of-shares-50-to-75-percent"],
         "identification": {"registration_number": "99999999", "country_registered": "Atlantis"}}]


class FakeHouse:
    def profile(self, n): return PROFILE if n == "00000001" else None
    def officers(self, n): return OFFICERS if n == "00000001" else []
    def filing_history(self, n, category="accounts"): return FILINGS if n == "00000001" else []
    def pscs(self, n): return PSCS if n == "00000001" else []
    def insolvency(self, n): return None
    def search(self, q, n=10):
        return [{"title": PROFILE["company_name"], "company_number": "00000001", "company_status": "active", "date_of_creation": "2018-03-01",
                 "address_snippet": "1 Demo Street, Leeds, LS1 1AA"}] if any(w in q.lower() for w in ("acme", "demo", "holdings")) else []


def fake_geocode(postcode): return {"lat": 53.7997, "lon": -1.5492} if postcode else None
