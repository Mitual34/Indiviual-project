"""Local settings store for the console: API keys and reference-list paths.
Held in memory; written to ~/.kyb_os/settings.json (owner-only permissions where the OS supports it) only when the
user ticks "Remember on this computer". The file is PLAIN TEXT, so keep that box off on shared machines."""
from __future__ import annotations
import json, pathlib


def mask(s: str | None) -> str:
    return "" if not s else "•" * max(0, len(s) - 4) + s[-4:]


class Store:
    def __init__(self, path=None):
        self.path = pathlib.Path(path) if path else pathlib.Path.home() / ".kyb_os" / "settings.json"
        self.data, self.persisted = {}, False
        try: self.data, self.persisted = json.loads(self.path.read_text(encoding="utf-8")), True
        except (OSError, ValueError): self.data = {}

    def update(self, **kw):
        for k, v in kw.items():
            if v is None: continue
            if v == "": self.data.pop(k, None)
            else: self.data[k] = v

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        try: self.path.chmod(0o600)
        except OSError: pass
        self.persisted = True

    def forget(self):
        self.data.clear()
        try: self.path.unlink()
        except OSError: pass
        self.persisted = False
