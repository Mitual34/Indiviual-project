"""Spins the real server on an ephemeral port (127.0.0.1) with a temp settings file; no network."""
import json, sys, threading, pathlib, urllib.request, urllib.error
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import pytest
from kyb_ingest import api
from kyb_ingest.server import make_server
from kyb_ingest.settings import Store

H = {"Content-Type": "application/json", "X-KYB-OS": "1"}


@pytest.fixture
def srv(tmp_path):
    (tmp_path / "kyb_os.html").write_text("<p>héllo</p>", encoding="utf-8")
    store = Store(tmp_path / "s.json"); ctx = api.Context(fake=True); api.rebuild(ctx, store)
    s = make_server(0, ctx, store, tmp_path); threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}", store, ctx, tmp_path
    s.shutdown(); s.server_close()


def call(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(), headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read() or b"{}") if "json" in r.headers.get("Content-Type", "") else r.read(), r.headers
    except urllib.error.HTTPError as e: return e.code, None, e.headers


def test_static_is_utf8_and_get_settings_never_returns_keys(srv):
    base, store, ctx, _ = srv
    code, body, h = call(base + "/kyb_os.html"); assert code == 200 and "charset=utf-8" in h["Content-Type"]
    assert call(base + "/api/settings")[1]["companies_house"]["set"] is False


def test_post_needs_custom_header_and_same_origin(srv):
    base, *_ = srv
    assert call(base + "/api/settings", {"companies_house_key": "x"}, {"Content-Type": "application/json"})[0] == 403          # no custom header
    assert call(base + "/api/settings", {"companies_house_key": "x"}, {**H, "Origin": "http://evil.example"})[0] == 403          # foreign origin
    assert call(base + "/api/settings", {}, {**H, "Host": "evil.example"})[0] == 403                                             # DNS-rebinding style
    assert call(base + "/api/settings", None, {"X-KYB-OS": "1"}, method="POST")[0] == 415


def test_save_key_masks_it_and_switches_mode(srv):
    base, store, ctx, _ = srv
    code, st, _ = call(base + "/api/settings", {"companies_house_key": "abcd-1234-efgh-9999"}, H)
    assert code == 200 and st["companies_house"] == dict(set=True, hint="•" * 15 + "9999", source="saved") and st["mode"] == "live"
    assert "abcd-1234" not in json.dumps(st) and "abcd-1234" not in json.dumps(call(base + "/api/settings")[1])
    assert not store.persisted and not store.path.exists()                       # not written without "remember"
    code, st, _ = call(base + "/api/settings", {"companies_house_key": ""}, H)     # clearing returns to the fake house (--fake) 
    assert st["companies_house"]["set"] is False and st["mode"] == "fake"


def test_remember_writes_owner_only_file_and_forget_deletes_it(srv):
    base, store, ctx, tmp = srv
    call(base + "/api/settings", {"companies_house_key": "k" * 20, "remember": True}, H)
    assert store.path.exists() and json.loads(store.path.read_text())["ch"] == "k" * 20 and store.persisted
    if sys.platform != "win32": assert oct(store.path.stat().st_mode)[-3:] == "600"
    assert Store(store.path).data["ch"] == "k" * 20                               # survives a restart
    call(base + "/api/settings", {"forget": True}, H); assert not store.path.exists() and store.data == {}


def test_rejects_bad_keys_and_paths(srv):
    base, store, ctx, tmp = srv
    assert call(base + "/api/settings", {"companies_house_key": "has space"}, H)[0] == 400
    assert call(base + "/api/settings", {"sanctions_path": str(tmp / "nope.csv")}, H)[0] == 400
    (tmp / "x.txt").write_text("a"); assert call(base + "/api/settings", {"sanctions_path": str(tmp / "x.txt")}, H)[0] == 400


def test_load_reference_list_and_unresolved_flow(srv):
    base, store, ctx, tmp = srv
    (tmp / "t.csv").write_text("id,schema,name,aliases,countries,identifiers,birth_date,dataset,first_seen,last_seen\nX1,Company,Shell Parent Limited,,Atlantis,99999999,,gb_fcdo_sanctions,2022-01-01,2025-01-01\n")
    code, st, _ = call(base + "/api/settings", {"sanctions_path": str(tmp / "t.csv")}, H)
    assert code == 200 and st["lists"]["sanctions"]["loaded"] is True
    row = call(base + "/api/company/00000001")[1]["row"]
    assert row["sanctions_proximity_flag"] == 1 and row["sanctions_status"] == "corroborated"          # PSC registration number matches


def test_connection_test_reports_readable_failures(srv):
    base, store, ctx, _ = srv
    assert call(base + "/api/test", {}, H)[1]["ok"] is True                              # demo mode
    class R:
        status_code = 400
        def json(self): return {"error": "Invalid Authorization header", "type": "ch:service"}
    class Bad:
        def profile(self, n): e = RuntimeError("x"); e.response = R(); raise e
    ctx.house, ctx.mode = Bad(), "live"
    out = call(base + "/api/test", {}, H)[1]
    assert out["ok"] is False and out["status"] == 400 and "no quotes or spaces" in out["message"] and "Invalid Authorization header" in out["message"]
    ctx.house = None; ctx.errors = {}
    assert "No Companies House key" in call(base + "/api/test", {}, H)[1]["message"]
