"""Local HTTP server: static console files + JSON API. Binds to 127.0.0.1 only.
Write endpoints (POST) require a custom header and, when the browser sends one, a same-origin Origin, so other web
pages cannot change your keys even if they know the port."""
from __future__ import annotations
import http.server, json, pathlib, threading
from . import api


def make_server(port, ctx, store, static_dir):
    lock = threading.Lock(); static_dir = str(pathlib.Path(static_dir))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=static_dir, **k)
        def log_message(self, fmt, *a): pass
        def end_headers(self): self.send_header("Cache-Control", "no-store"); super().end_headers()
        def guess_type(self, path):
            t = super().guess_type(path)
            return t + "; charset=utf-8" if t.split(";")[0] in ("text/html", "text/css", "text/plain", "application/json", "text/javascript", "application/javascript") else t
        def _host(self): return (self.headers.get("Host") or "")
        def _host_ok(self): return self._host().split(":")[0] in ("localhost", "127.0.0.1")
        def _json(self, code, body):
            data = json.dumps(body).encode(); self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            if not self._host_ok(): self.send_error(403); return
            if self.path.startswith("/api/settings"):
                with lock: self._json(200, api.settings_state(ctx, store)); return
            if self.path.startswith("/api/"):
                with lock: code, body = api.handle(ctx, self.path)
                self._json(code, body); return
            if self.path in ("/", ""): self.send_response(302); self.send_header("Location", "/kyb_os.html"); self.end_headers(); return
            super().do_GET()
        def do_POST(self):
            if not self._host_ok(): self.send_error(403); return
            origin = self.headers.get("Origin")
            if self.headers.get("X-KYB-OS") != "1" or (origin and origin != f"http://{self._host()}"): self.send_error(403); return
            if not (self.headers.get("Content-Type") or "").startswith("application/json"): self.send_error(415); return
            n = int(self.headers.get("Content-Length") or 0)
            if n > 20000: self.send_error(413); return
            try: body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError: self._json(400, {"error": "Invalid JSON."}); return
            with lock:
                if self.path == "/api/settings": code, out = api.apply_settings(ctx, store, body)
                elif self.path == "/api/test": code, out = api.test_connection(ctx)
                else: code, out = 404, {"error": "Unknown endpoint."}
            self._json(code, out)

    http.server.ThreadingHTTPServer.allow_reuse_address = True
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
