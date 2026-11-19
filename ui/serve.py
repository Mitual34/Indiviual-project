"""Serve the KYB-OS console on http://localhost:8000 with a local API for live checks.
    python ui/serve.py              # then open Settings in the console and paste your Companies House API key
    python ui/serve.py 8080         # another port
    python ui/serve.py --fake       # fictional company 00000001, no key or network needed
Keys entered in Settings stay in this process (and ~/.kyb_os/settings.json only if you tick 'Remember'). The
COMPANIES_HOUSE_API_KEY environment variable is also honoured. Binds to 127.0.0.1 only. Stop with Ctrl+C."""
import argparse, pathlib, sys, threading, webbrowser
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kyb_ingest import api
from kyb_ingest.server import make_server
from kyb_ingest.settings import Store

ap = argparse.ArgumentParser(description="KYB-OS local server")
ap.add_argument("port", nargs="?", type=int, default=8000); ap.add_argument("--fake", action="store_true"); ap.add_argument("--no-browser", action="store_true")
args = ap.parse_args()
store = Store(); ctx = api.Context(fake=args.fake); api.rebuild(ctx, store)
try: srv = make_server(args.port, ctx, store, pathlib.Path(__file__).parent)
except OSError as e: sys.exit(f"Could not start on port {args.port} ({e}). Try another port, e.g. python ui/serve.py {args.port + 1}")
hash_ = "#lookup" if ctx.mode != "off" else "#config"
url = f"http://localhost:{args.port}/kyb_os.html{hash_}"
print(f"KYB-OS running at {url}  [lookup mode: {ctx.mode}]  (Ctrl+C to stop)")
if ctx.mode == "off": print("No API key yet: open Settings in the console to add one.")
if not args.no_browser: threading.Timer(0.5, lambda: webbrowser.open(url)).start()
try: srv.serve_forever()
except KeyboardInterrupt: print("\nStopped.")
