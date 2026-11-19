"""Builds ui/uk.json (simplified GB local-authority outlines, projected to SVG units) and adds SIMULATED locations to the
demo cases in ui/data.json. Boundaries: martinjc/UK-GeoJSON (2013 local authority districts; Contains OS data (c) Crown
copyright and database right). Great Britain only: Northern Ireland is not in this source. Case locations are placed
deterministically at random and are NOT real addresses."""
import json, math, hashlib, pathlib, sys, random
from shapely.geometry import shape, Point
HERE = pathlib.Path(__file__).parent
src = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/lad.json"))["features"]
geoms = [shape(f["geometry"]).simplify(0.012, preserve_topology=True) for f in src]
minx = min(g.bounds[0] for g in geoms); maxx = max(g.bounds[2] for g in geoms)
miny = min(g.bounds[1] for g in geoms); maxy = max(g.bounds[3] for g in geoms)
cosl = math.cos(math.radians((miny + maxy) / 2)); K = 520 / ((maxx - minx) * cosl)
P = lambda lon, lat: ((lon - minx) * cosl * K + 20, (maxy - lat) * K + 20)
W, H = 560, round((maxy - miny) * K + 40)
lads, polys = [], []
for f, g in zip(src, geoms):
    parts = [g] if g.geom_type == "Polygon" else list(g.geoms)
    parts = [p for p in parts if p.area > 0.0004] or [max(parts, key=lambda p: p.area)]
    d = ""
    for p in parts:
        for ring in [p.exterior, *p.interiors]:
            d += "M" + " ".join("%.1f,%.1f" % P(*c) for c in ring.coords[:-1]) + "Z"
    rp = max(parts, key=lambda p: p.area).representative_point(); cx, cy = P(rp.x, rp.y)
    lads.append(dict(c=f["properties"]["LAD13CD"], n=f["properties"]["LAD13NM"], d=d, cx=round(cx, 1), cy=round(cy, 1), a=g.area))
    polys.append(parts)
json.dump(dict(w=W, h=H, proj=dict(minx=minx, maxy=maxy, cosl=cosl, K=K, off=20), lads=[{**l, "a": round(l["a"], 5)} for l in lads]), open(HERE / "uk.json", "w"), separators=(",", ":"))

data = json.load(open(HERE / "data.json")); cases = data["cases"]
hsh = lambda s: int(hashlib.md5(s.encode()).hexdigest(), 16)
w = [(1 / max(l["a"], 1e-4)) ** 0.35 for l in lads]; tot = sum(w)
def pick(h):
    r = (h % 10**6) / 10**6 * tot
    for i, x in enumerate(w):
        r -= x
        if r <= 0: return i
    return len(w) - 1
def point_in(i, seed):
    rnd = random.Random(seed); big = max(polys[i], key=lambda p: p.area); a, b, c, d = big.bounds
    for _ in range(200):
        x, y = rnd.uniform(a, c), rnd.uniform(b, d)
        if big.contains(Point(x, y)): return P(x, y)
    rp = big.representative_point(); return P(rp.x, rp.y)
# four simulated shared addresses (a real pipeline would match registered-office addresses from Companies House)
streets = ["Fenwick Row", "Calder Court", "Marlow Yard", "Saltmere House"]
anchor_lads = [pick(hsh("anchor%d" % k)) for k in range(4)]
anchors = [point_in(i, "a%d" % i) for i in anchor_lads]
for c in cases:
    h = hsh(c["id"]); k = h % 4 if (h >> 12) % 100 < 22 else None
    if k is not None:
        i = anchor_lads[k]; x, y = anchors[k]; rnd = random.Random(h); x += rnd.uniform(-1.2, 1.2); y += rnd.uniform(-1.2, 1.2)
        c["addr"] = k; c["addrname"] = "%d %s (demo)" % (10 + k * 7, streets[k])
    else:
        i = pick(h); x, y = point_in(i, h); c["addr"] = None; c["addrname"] = None
    c["lad"] = i; c["x"] = round(x, 1); c["y"] = round(y, 1)
data["addresses"] = [dict(k=k, name="%d %s (demo)" % (10 + k * 7, streets[k]), lad=anchor_lads[k], x=round(anchors[k][0], 1), y=round(anchors[k][1], 1)) for k in range(4)]
json.dump(data, open(HERE / "data.json", "w"), separators=(",", ":"))
import collections; print("map %dx%d" % (W, H), "uk.json KB", (HERE / "uk.json").stat().st_size // 1024, "data.json KB", (HERE / "data.json").stat().st_size // 1024,
      collections.Counter(c["addr"] for c in cases))
