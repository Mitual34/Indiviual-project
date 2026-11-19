"""Assembles ui/kyb_os.html (self-contained) from the template, data.json and uk.json."""
import pathlib
H = pathlib.Path(__file__).parent
t = (H / "kyb_os.template.html").read_text()
out = '<meta charset="utf-8">\n' + t.replace("__DATA__", (H / "data.json").read_text()).replace("__GEO__", (H / "uk.json").read_text())
(H / "kyb_os.html").write_text(out); print("kyb_os.html KB", len(out) // 1024)
