"""Offline tests: fake HTTP getters and a tiny fictional reference list. No network, no API keys."""
import csv, sys, pathlib
from datetime import date
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from kyb_ingest import companies_house as ch
from kyb_ingest.http import RateLimiter
from kyb_ingest.matching import name_score, normalise_name
from kyb_ingest.opensanctions import SanctionsIndex, flag_from_candidates
from kyb_ingest.gdelt import score_articles, build_query, GDELTDoc
from kyb_ingest.jurisdiction import JurisdictionPolicy
from kyb_ingest.pipeline import build_feature_row
from kyb_ingest.gleif import GLEIF

AS_OF = date(2025, 6, 30)
PROFILE = {"company_name": "Acme Holdings Limited", "company_status": "active", "date_of_creation": "2018-03-01",
           "sic_codes": ["01110", "62020"], "type": "ltd", "accounts": {"overdue": False}}
OFFICERS = [{"name": "DOE, Jane", "appointed_on": "2025-01-10", "date_of_birth": {"year": 1970}, "country_of_residence": "Atlantis"},
            {"name": "ROE, Rich", "appointed_on": "2015-01-01", "resigned_on": "2024-12-01", "country_of_residence": "United Kingdom"},
            {"name": "OLD, Ollie", "appointed_on": "2010-01-01", "resigned_on": "2019-01-01"}]
FILINGS = [  # accounts made up to 31 Mar each year; deadline +9 months = 31 Dec
    {"type": "AA", "date": "2021-01-15", "description_values": {"made_up_date": "2020-03-31"}},   # late (due 2020-12-31) but before lookback
    {"type": "AA", "date": "2023-01-20", "description_values": {"made_up_date": "2022-03-31"}},   # late (due 2022-12-31), in lookback
    {"type": "AA", "date": "2023-11-01", "description_values": {"made_up_date": "2023-03-31"}},   # on time
    {"type": "AA", "date": "2025-02-01", "description_values": {"made_up_date": "2024-03-31"}},   # late (due 2024-12-31), in lookback
]


class FakeCH(ch.CompaniesHouse):
    def __init__(self, found=True): self.found = found
    def profile(self, n): return PROFILE if self.found else None
    def officers(self, n): return OFFICERS
    def filing_history(self, n, category="accounts"): return FILINGS
    def pscs(self, n): return [{"name": "Shell Parent Ltd", "kind": "corporate-entity-person-with-significant-control",
                                 "identification": {"registration_number": "99999999", "country_registered": "Atlantis"}}]


def write_targets(tmp_path):
    p = tmp_path / "targets.csv"
    rows = [dict(id="X1", schema="Company", name="Shell Parent Limited", aliases="Shell Parent Holdings", countries="Atlantis",
                 identifiers="99999999", birth_date="", dataset="gb_fcdo_sanctions", first_seen="2022-03-01", last_seen="2025-01-01"),
            dict(id="X2", schema="Person", name="Jane Doe", aliases="", countries="Atlantis", identifiers="",
                 birth_date="1970-05-02", dataset="peps", first_seen="2020-01-01", last_seen="2025-01-01"),
            dict(id="X3", schema="Company", name="Completely Different Trading", aliases="", countries="Ruritania", identifiers="",
                 birth_date="", dataset="gb_fcdo_sanctions", first_seen="2020-01-01", last_seen="2025-01-01")]
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return p


def test_features_from_registry_data():
    assert ch.company_age_years(PROFILE, AS_OF) == 7.33
    assert ch.industry(PROFILE) == "01110"                       # leading zero preserved
    assert ch.officer_changes(OFFICERS, AS_OF) == 2              # Jane appointed, Rich resigned inside 365d
    assert ch.late_filings(PROFILE, FILINGS, AS_OF) == 2         # 2023-01 and 2025-02; 2021 is outside the 3y lookback
    assert ch.late_filings(PROFILE, None, AS_OF) is None and ch.officer_changes(None, AS_OF) is None
    assert ch.late_filings({**PROFILE, "accounts": {"overdue": True}}, [], AS_OF) == 1


def test_first_accounts_get_21_months():
    prof = {**PROFILE, "date_of_creation": "2022-01-01"}
    f = [{"type": "AA", "date": "2023-09-01", "description_values": {"made_up_date": "2022-12-31"}}]  # +9m would be 2023-09-30 => not late anyway
    f2 = [{"type": "AA", "date": "2023-10-15", "description_values": {"made_up_date": "2022-06-30"}}]  # +9m = 2023-03-31 but 21m rule = 2023-10-01 -> late
    assert ch.late_filings(prof, f, AS_OF) == 0 and ch.late_filings(prof, f2, AS_OF) == 1


def test_name_normalisation_and_scoring():
    assert normalise_name("ACME Holdings Ltd.") == "acme holdings"
    assert name_score("Shell Parent Limited", "SHELL PARENT LTD") == 1.0
    assert name_score("Jane Doe", "DOE, Jane", "person") == 1.0
    assert name_score("Acme Holdings", "Completely Different Trading") < 0.5


def test_sanctions_matching_corroboration_and_unresolved_policy(tmp_path):
    idx = SanctionsIndex.from_csv(write_targets(tmp_path), "uk_fcdo_sanctions")
    hit = idx.match("Shell Parent Ltd", "company", country="Atlantis", company_number="99999999")
    assert hit and hit[0].status == "corroborated" and "identifier match" in hit[0].reasons
    weak = idx.match("Shell Parent Ltd", "company")                      # name only -> candidate, not a flag
    assert weak[0].status == "candidate" and flag_from_candidates(weak) == (None, "unresolved_candidate")
    assert flag_from_candidates(weak, "positive")[0] == 1 and flag_from_candidates([]) == (0, "no_match")
    assert idx.match("Totally Unrelated Plc", "company") == []


def test_person_corroboration_needs_birth_year(tmp_path):
    idx = SanctionsIndex.from_csv(write_targets(tmp_path), "peps")
    assert idx.match("Jane Doe", "person", birth_year=1970)[0].status == "corroborated"
    assert idx.match("Jane Doe", "person", birth_year=1985)[0].status == "candidate"


def test_gdelt_query_and_title_filter():
    assert build_query("Acme Holdings Limited").startswith('"Acme Holdings Limited" (fraud OR')
    arts = [{"title": "Acme Holdings fined over bribery", "domain": "a.com", "url": "u1"},
            {"title": "Holdings of Acme street fraud", "domain": "b.com", "url": "u2"},   # contains tokens (order-insensitive) -> kept
            {"title": "Unrelated Corp scandal", "domain": "c.com", "url": "u3"}]
    s = score_articles(arts, "Acme Holdings Limited")
    assert s["adverse_media_count"] == 2 and s["adverse_media_domains"] == 2
    assert GDELTDoc(get=lambda url, params=None: {"articles": arts}).adverse_media("Acme Holdings Limited")["adverse_media_count"] == 2
    assert GDELTDoc(get=lambda url, params=None: None).adverse_media("X") is None


def test_rate_limiter_sleeps_when_window_full():
    t = [0.0]; slept = []
    def sleep(s): slept.append(s); t[0] += s
    rl = RateLimiter(2, 10, clock=lambda: t[0], sleep=sleep)
    rl.wait(); rl.wait(); rl.wait()
    assert slept == [10.0]


def test_pipeline_keeps_unknowns_and_flags_with_evidence(tmp_path):
    p = tmp_path / "policy.csv"; p.write_text("country,list_name,effective_from,effective_to\nAtlantis,test list,2024-01-01,\n")
    row = build_feature_row("12345678", AS_OF, FakeCH(), SanctionsIndex.from_csv(write_targets(tmp_path), "uk_fcdo_sanctions"),
                            SanctionsIndex.from_csv(write_targets(tmp_path), "peps"), None, JurisdictionPolicy.load(p),
                            GLEIF(get=lambda url, params=None: {"data": [{"id": "L1", "attributes": {"lei": "L1",
                                 "entity": {"legalName": {"name": "Acme Holdings Limited"}, "registeredAs": "12345678"}}}]}))
    assert row["late_filings"] == 2 and row["officer_changes"] == 2 and row["industry"] == "01110"
    assert row["jurisdiction_flag"] == 1 and row["jurisdiction_lists"] == ["test list"]
    assert row["sanctions_proximity_flag"] == 1 and row["sanctions_status"] == "corroborated"   # corporate PSC matched by reg. number
    assert row["pep_flag"] == 1 and row["pep_status"] == "corroborated"                           # Jane Doe: name + birth year 1970
    assert row["adverse_media_count"] is None and row["lei"] == "L1"
    off = build_feature_row("12345678", AS_OF, FakeCH())
    assert off["sanctions_proximity_flag"] is None and off["jurisdiction_flag"] is None
    assert build_feature_row("0", AS_OF, FakeCH(found=False))["found"] is False
    assert JurisdictionPolicy.load(tmp_path / "missing.csv") is None


def test_pep_name_hit_without_birth_year_stays_unknown(tmp_path):
    class NoDOB(FakeCH):
        def officers(self, n): return [{k: v for k, v in o.items() if k != "date_of_birth"} for o in OFFICERS]
    row = build_feature_row("12345678", AS_OF, NoDOB(), None, SanctionsIndex.from_csv(write_targets(tmp_path), "peps"))
    assert row["pep_flag"] is None and row["pep_status"] == "unresolved_candidate"
    row2 = build_feature_row("12345678", AS_OF, NoDOB(), None, SanctionsIndex.from_csv(write_targets(tmp_path), "peps"), unresolved="negative")
    assert row2["pep_flag"] == 0


def test_api_key_prompt_and_env(monkeypatch):
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", " abc ")
    assert ch.get_api_key() == "abc"
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY")
    monkeypatch.setattr(ch.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(ch.getpass, "getpass", lambda prompt: "typed-key")
    assert ch.get_api_key() == "typed-key"
    monkeypatch.setattr(ch.sys.stdin, "isatty", lambda: False)
    import pytest
    with pytest.raises(RuntimeError): ch.get_api_key()
