import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from kyb_ingest import api, fake


def ctx(**k): return api.Context(house=fake.FakeHouse(), mode="fake", geocode=fake.fake_geocode, **k)


def test_status_and_off_mode():
    assert api.handle(ctx(), "/api/status")[1]["mode"] == "fake"
    code, body = api.handle(api.Context(), "/api/company/00000001")
    assert code == 503 and "off" in body["error"]


def test_search_and_validation():
    code, b = api.handle(ctx(), "/api/search?q=acme"); assert code == 200 and b["items"][0]["number"] == "00000001"
    assert api.handle(ctx(), "/api/search?q=a")[0] == 400
    assert api.handle(ctx(), "/api/search?q=zzzz")[1]["items"] == []
    for bad in ("/api/company/../etc", "/api/company/abc%20def", "/api/company/123456789"):
        assert api.handle(ctx(), bad)[0] in (400, 404)


def test_company_payload_features_officers_and_geo():
    code, b = api.handle(ctx(), "/api/company/00000001")
    assert code == 200 and b["profile"]["name"].startswith("ACME") and b["profile"]["office"].endswith("LS1 1AA")
    r = b["row"]; assert r["industry"] == "01110" and r["late_filings"] is not None and r["officer_changes"] is not None
    assert r["jurisdiction_flag"] is None and r["sanctions_status"] == "source_not_loaded" and r["adverse_media_count"] is None   # unknowns stay unknown
    assert len(b["officers"]) == 3 and b["pscs"][0]["control"] == ["ownership of shares 50 to 75 percent"] and b["geo"]["lat"] > 53
    assert "birth_year" in b["officers"][0] and "date_of_birth" not in b["officers"][0]


def test_numeric_short_number_is_zero_padded_and_unknown_is_404():
    assert api.handle(ctx(), "/api/company/1")[0] == 400                   # too short to be a company number
    assert api.handle(ctx(), "/api/company/00000009")[0] == 404


def test_client_errors_are_mapped_without_leaking_secrets():
    class R:  # stands in for requests.Response
        status_code = 403
    class Boom(fake.FakeHouse):
        def profile(self, n):
            e = RuntimeError("secret-key-123 in url"); e.response = R(); raise e
    code, b = api.handle(api.Context(house=Boom(), mode="live"), "/api/company/00000001")
    assert code == 502 and "secret" not in str(b) and "rejected" in b["error"]


def test_cached_house_calls_each_endpoint_once():
    calls = []
    class Spy(fake.FakeHouse):
        def profile(self, n): calls.append("profile"); return super().profile(n)
    api.handle(api.Context(house=Spy(), mode="fake"), "/api/company/00000001")
    assert calls == ["profile"]
