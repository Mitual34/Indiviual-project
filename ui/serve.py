"""Serve the KYB-OS console on http://localhost:8000 with an optional live Companies House API.
    python ui/serve.py                 # asks for your Companies House API key (hidden input); Enter skips live lookup
    python ui/serve.py 8080            # another port
    python ui/serve.py --fake          # fictional company 00000001 for trying the Lookup view, no key or network
    python ui/serve.py --sanctions targets.csv [--peps peps.csv] [--policy policy.csv]
The key stays in this process; the browser only talks to /api/*. Binds to 127.0.0.1 only. Stop with Ctrl+C."""
import argparse, http.server, json, pathlib, sys, threading, webbrowser
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kyb_ingest import api, fake
from kyb_ingest import companies_house as ch

HERE = pathlib.Path(__file__).parent
ap = argparse.ArgumentParser(description="KYB-OS local server")
ap.add_argument("port", nargs="?", type=int, default=8000); ap.add_argument("--fake", action="store_true"); ap.add_argument("--no-live", action="store_true")
ap.add_argument("--no-browser", action="store_true"); ap.add_argument("--sanctions"); ap.add_argument("--peps"); ap.add_argument("--policy")
ap.add_argument("--no-geocode", action="store_true", help="do not call api.postcodes.io for map pins")
args = ap.parse_args()


def build_context():
    ctx = api.Context()
    if args.fake: ctx.house, ctx.mode, ctx.geocode = fake.FakeHouse(), "fake", fake.fake_geocode
    elif not args.no_live:
        try: ctx.house, ctx.mode = ch.CompaniesHouse(), "live"
        except RuntimeError as e: print(f"Live lookup off: {e}")
    if args.sanctions or args.peps:
        from kyb_ingest.opensanctions import SanctionsIndex
        if args.sanctions: ctx.sanctions = SanctionsIndex.from_csv(args.sanctions, "sanctions")
        if args.peps: ctx.peps = SanctionsIndex.from_csv(args.peps, "peps")
    if args.policy:
        from kyb_ingest.jurisdiction import JurisdictionPolicy
        ctx.policy = JurisdictionPolicy.load(args.policy)
    if ctx.mode == "live" and not args.no_geocode:
        from kyb_ingest.http import make_getter, RateLimiter
        get = make_getter(limiter=RateLimiter(30, 60))
        def geocode(pc):
            try:
                r = get("https://api.postcodes.io/postcodes/" + pc.replace(" ", ""))
                return {"lat": r["result"]["latitude"], "lon": r["result"]["longitude"]} if r and r.get("result") else None
            except Exception: return None
        ctx.geocode = geocode
    return ctx


CTX, LOCK = build_context(), threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(HERE), **k)
    def end_headers(self): self.send_header("Cache-Control", "no-store"); super().end_headers()
    def guess_type(self, path):
        t = super().guess_type(path)
        return t + "; charset=utf-8" if t.split(";")[0] in ("text/html", "text/css", "text/plain", "application/json", "text/javascript", "application/javascript") else t
    def log_message(self, fmt, *a): pass
    def _host_ok(self): return (self.headers.get("Host") or "").split(":")[0] in ("localhost", "127.0.0.1")
    def do_GET(self):
        if not self._host_ok(): self.send_error(403); return          # blocks DNS-rebinding style requests
        if self.path.startswith("/api/"):
            with LOCK: code, body = api.handle(CTX, self.path)
            data = json.dumps(body).encode(); self.send_response(code)
            self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if self.path in ("/", ""): self.send_response(302); self.send_header("Location", "/kyb_os.html"); self.end_headers(); return
        super().do_GET()
    def do_POST(self): self.send_error(405)


http.server.ThreadingHTTPServer.allow_reuse_address = True
with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as srv:
    url = f"http://localhost:{args.port}/kyb_os.html#lookup"
    print(f"KYB-OS running at {url}  [lookup mode: {CTX.mode}]  (Ctrl+C to stop)")
    if not args.no_browser: threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
