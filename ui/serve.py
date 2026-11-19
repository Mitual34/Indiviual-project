"""Serve the KYB-OS console on http://localhost:8000 (no dependencies beyond the Python standard library).
    python ui/serve.py            # port 8000, opens your browser
    python ui/serve.py 8080       # another port
Stop with Ctrl+C. Binds to 127.0.0.1 only, so it is not reachable from other machines."""
import http.server, pathlib, socketserver, sys, threading, webbrowser

HERE = pathlib.Path(__file__).parent
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(HERE), **k)
    def end_headers(self): self.send_header("Cache-Control", "no-store"); super().end_headers()
    def log_message(self, fmt, *args): pass


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", port), Handler) as srv:
    url = f"http://localhost:{port}/kyb_os.html"
    print(f"KYB-OS running at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv: threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
