#!/usr/bin/env python3
"""Generate an ILLUSTRATIVE synthetic pipeline network for MethaTrace.

Reads  data/chakan_pipelines.geojson            (never modified)
Writes data/chakan_pipelines_simulated.geojson  (new file)

The original pipeline IDs, properties and feature order are preserved; only the
geometries are replaced. The generated routes are synthetic and illustrative.
They do NOT represent real underground infrastructure or verified road
alignments.

Approach (all deterministic, driven by one seeded random.Random):
  1. Work in a local metric plane (equirectangular) so distances and angles are
     meaningful, then convert back to WGS84 [lon, lat].
  2. Four irregular trunks (two west-east, two south-north) built from
     sinusoid + noise waypoints. Crossings are "noded": the crossing point is
     inserted as a shared vertex in both trunks.
  3. Tap junctions are placed along the trunks (also inserted as trunk vertices).
  4. Distribution lines are grown outward from the taps as a branching network:
     each line joins a parent junction to a new junction (or, ~12% of the time,
     to an existing junction to close a loop), with 1-3 gentle bends. Candidates
     are rejected if they cross other lines, leave the area, hug other lines,
     or leave at a tiny angle to an existing line at a junction.
  5. Trunk features (sorted by ID) and distribution features (sorted by ID) are
     matched to the generated lines in generation order.

Only the standard library and shapely (already a GeoPandas dependency) are used.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

from shapely.geometry import LineString, Point

GENERATOR_VERSION = "1.1.0"
DEFAULT_SEED = 42
EXPECTED_TRUNKS = 4

ID_CANDIDATES = ("pipeline_id", "pipe_id", "id", "ID", "PipelineID", "pipelineId", "segment_id")
TYPE_CANDIDATES = ("pipeline_type", "type", "pipe_type", "category", "line_type", "class", "pipeline_class")

DISCLAIMER = (
    "Geometry in this file is synthetic and illustrative only. It was generated "
    "for the MethaTrace prototype and does not represent real underground "
    "infrastructure or verified road alignments."
)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def natural_key(value):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(value))]


def unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 0 else (1.0, 0.0)


def rot(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def angle_between(u, v):
    return math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1])))


def iter_coords(c):
    if c and isinstance(c[0], (int, float)):
        yield c
    else:
        for x in c:
            yield from iter_coords(x)


def insert_vertex(coords, p, tol=1e-6):
    """Insert point p (lying on the polyline) as a vertex; no-op if already there."""
    for c in coords:
        if math.dist(c, p) <= tol:
            return coords
    d = LineString(coords).project(Point(p))
    acc = 0.0
    out = list(coords)
    for i in range(len(coords) - 1):
        seg = math.dist(coords[i], coords[i + 1])
        if acc + seg >= d - 1e-9:
            out.insert(i + 1, p)
            return out
        acc += seg
    raise RuntimeError("could not insert vertex")


def point_parts(geom):
    """Return list of (x, y) if geom is only points, else None (overlap)."""
    out = []
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type != "Point":
            return None
        out.append((g.x, g.y))
    return out


class LocalProjection:
    def __init__(self, bbox):
        minx, miny, maxx, maxy = bbox
        self.lon0, self.lat0 = (minx + maxx) / 2, (miny + maxy) / 2
        self.kx = 111320.0 * math.cos(math.radians(self.lat0))
        self.ky = 110574.0

    def fwd(self, lon, lat):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    def inv(self, x, y):
        return (self.lon0 + x / self.kx, self.lat0 + y / self.ky)


# --------------------------------------------------------------------------- #
# reading the source
# --------------------------------------------------------------------------- #
def detect_fields(features, id_field=None, type_field=None):
    props = [f.get("properties") or {} for f in features]
    if type_field is None:
        keys = list(TYPE_CANDIDATES) + [k for k in props[0] if k not in TYPE_CANDIDATES]
        for k in keys:
            vals = [str(p.get(k, "")).lower() for p in props]
            if any("trunk" in v for v in vals) and any("distribution" in v for v in vals):
                type_field = k
                break
        else:
            raise ValueError("Cannot detect the pipeline-type property; pass --type-field.")
    if id_field is None:
        for k in ID_CANDIDATES:
            vals = [p.get(k) for p in props]
            if all(v is not None for v in vals) and len({str(v) for v in vals}) == len(vals):
                id_field = k
                break
        else:
            raise ValueError("Cannot detect the pipeline-ID property; pass --id-field.")
    return id_field, type_field


# --------------------------------------------------------------------------- #
# trunks
# --------------------------------------------------------------------------- #
def build_trunks(rng, box):
    """Two west-east and two south-north trunks.

    Bend amplitude/wavelength are set in metres relative to the SHORTER side of
    the area, so slopes stay realistic when the area is tall and narrow.
    """
    xmin, ymin, xmax, ymax = box
    W, H = xmax - xmin, ymax - ymin
    um = min(W, H)
    specs = [("h", rng.uniform(0.18, 0.28)), ("h", rng.uniform(0.68, 0.80)),
             ("v", rng.uniform(0.22, 0.34)), ("v", rng.uniform(0.66, 0.78))]
    trunks = []
    for orient, base in specs:
        span, cross = (W, H) if orient == "h" else (H, W)
        lo_a, lo_c = (xmin, ymin) if orient == "h" else (ymin, xmin)
        n = max(8, min(14, round(span / (0.18 * um))))
        phase = rng.uniform(0, 2 * math.pi)
        wl = rng.uniform(0.7, 1.1) * um
        amp = rng.uniform(0.08, 0.14) * um
        pts = []
        for i in range(n):
            t = i / (n - 1)
            if 0 < i < n - 1:
                t += rng.uniform(-0.3, 0.3) / (n - 1)
            along = (0.015 + 0.97 * t) * span
            off = amp * math.sin(2 * math.pi * along / wl + phase) + rng.uniform(-0.04, 0.04) * um
            cf = min(0.97, max(0.03, base + off / cross))
            a, c = lo_a + along, lo_c + cf * cross
            pts.append((a, c) if orient == "h" else (c, a))
        trunks.append(pts)
    return trunks


def node_trunk_crossings(trunks):
    junctions = []
    for i in range(len(trunks)):
        for j in range(i + 1, len(trunks)):
            inter = LineString(trunks[i]).intersection(LineString(trunks[j]))
            pts = point_parts(inter) if not inter.is_empty else []
            for p in pts or []:
                trunks[i] = insert_vertex(trunks[i], p)
                trunks[j] = insert_vertex(trunks[j], p)
                junctions.append(p)
    return junctions


# --------------------------------------------------------------------------- #
# distribution network
# --------------------------------------------------------------------------- #
class Builder:
    MIN_ANGLE = math.radians(28)

    def __init__(self, rng, box, trunks, junctions):
        self.rng = rng
        self.box = box
        xmin, ymin, xmax, ymax = box
        W, H = xmax - xmin, ymax - ymin
        self.inner = (xmin + 0.008 * W, ymin + 0.008 * H, xmax - 0.008 * W, ymax - 0.008 * H)
        self.scale = 0.085 * min(W, H)
        self.clear0 = 0.25 * self.scale
        self.sep0 = 0.35 * self.scale
        self.trunks = trunks
        self.junctions = junctions
        self.nodes, self.dirs, self.base, self.deg = [], [], [], []
        self.edges, self.lines = [], []
        self.adj = set()
        self.obstacles = []  # (LineString, bounds, set(node idx))

    # -- node management ---------------------------------------------------
    def add_node(self, p, dirs, base):
        self.nodes.append(p)
        self.dirs.append(dirs)
        self.base.append(base)
        self.deg.append(0)
        return len(self.nodes) - 1

    def place_taps(self):
        counts = [5, 4, 5, 4]
        taken = list(self.junctions)
        sep = 0.5 * self.scale
        pending = []  # (trunk idx, point, tangent)
        for ti, trunk in enumerate(self.trunks):
            line = LineString(trunk)
            n = counts[ti % len(counts)]
            for k in range(n):
                f = (k + 0.5) / n + self.rng.uniform(-0.25, 0.25) / n
                d = f * line.length
                p = line.interpolate(d)
                pt = (p.x, p.y)
                if any(math.dist(pt, q) < sep for q in taken):
                    continue
                a = line.interpolate(max(0.0, d - 20))
                b = line.interpolate(min(line.length, d + 20))
                tan = unit(b.x - a.x, b.y - a.y)
                taken.append(pt)
                pending.append((ti, pt, tan))
        tap_nodes = {ti: set() for ti in range(len(self.trunks))}
        for ti, pt, tan in pending:
            self.trunks[ti] = insert_vertex(self.trunks[ti], pt)
            perp = (-tan[1], tan[0])
            idx = self.add_node(pt, [tan, (-tan[0], -tan[1])], [perp, (-perp[0], -perp[1])])
            tap_nodes[ti].add(idx)
        for ti, trunk in enumerate(self.trunks):
            g = LineString(trunk)
            self.obstacles.append((g, g.bounds, tap_nodes[ti]))
        return [idx for ti in tap_nodes for idx in sorted(tap_nodes[ti])]

    # -- geometry ----------------------------------------------------------
    def route(self, a, b):
        L = math.dist(a, b)
        d = unit(b[0] - a[0], b[1] - a[1])
        n = max(1, min(4, round(L / (0.4 * self.scale)))) + self.rng.choice([0, 0, 1])
        n = min(n, 4)
        pts = [a]
        for k in range(n):
            t = (k + 1) / (n + 1) + self.rng.uniform(-0.08, 0.08)
            off = self.rng.uniform(-0.18, 0.18) * L
            pts.append((a[0] + d[0] * L * t - d[1] * off, a[1] + d[1] * L * t + d[0] * off))
        pts.append(b)
        return pts

    def inside(self, p):
        x0, y0, x1, y1 = self.inner
        return x0 <= p[0] <= x1 and y0 <= p[1] <= y1

    def acceptable(self, pts, s, e, relax):
        if not all(self.inside(p) for p in pts):
            return False
        line = LineString(pts)
        if not line.is_simple:
            return False
        sp = self.nodes[s]
        ep = self.nodes[e] if e is not None else None
        d0 = unit(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
        if any(angle_between(d0, v) < self.MIN_ANGLE for v in self.dirs[s]):
            return False
        if e is not None:
            d1 = unit(pts[-2][0] - pts[-1][0], pts[-2][1] - pts[-1][1])
            if any(angle_between(d1, v) < self.MIN_ANGLE for v in self.dirs[e]):
                return False
        clear = self.clear0 * relax
        bx0, by0, bx1, by1 = line.bounds
        for g, gb, nodeset in self.obstacles:
            if gb[0] > bx1 + clear or gb[2] < bx0 - clear or gb[1] > by1 + clear or gb[3] < by0 - clear:
                continue
            inter = line.intersection(g)
            if not inter.is_empty:
                parts = point_parts(inter)
                if parts is None:
                    return False
                for q in parts:
                    if not (math.dist(q, sp) < 0.05 or (ep and math.dist(q, ep) < 0.05)):
                        return False
            incident = s in nodeset or (e is not None and e in nodeset)
            if not incident and line.distance(g) < clear:
                return False
        return True

    def commit(self, pts, s, e_new_or_idx, is_new):
        if is_new:
            last = unit(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
            e = self.add_node(pts[-1], [(-last[0], -last[1])], [last])
        else:
            e = e_new_or_idx
            back = unit(pts[-2][0] - pts[-1][0], pts[-2][1] - pts[-1][1])
            self.dirs[e].append(back)
        first = unit(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
        self.dirs[s].append(first)
        self.deg[s] += 1
        self.deg[e] += 1
        self.adj.add(frozenset((s, e)))
        g = LineString(pts)
        self.obstacles.append((g, g.bounds, {s, e}))
        self.edges.append((s, e))
        self.lines.append(pts)

    # -- growth ------------------------------------------------------------
    def grow(self, taps, n_edges):
        rng = self.rng
        # seed edges leaving the trunks
        for s in taps:
            if len(self.edges) >= n_edges:
                break
            for _ in range(40):
                base = rng.choice(self.base[s])
                h = rot(base, rng.uniform(-0.45, 0.45))
                ln = self.scale * rng.uniform(0.7, 1.4)
                b = (self.nodes[s][0] + h[0] * ln, self.nodes[s][1] + h[1] * ln)
                pts = self.route(self.nodes[s], b)
                if self.acceptable(pts, s, None, 1.0) and self.min_sep_ok(b, s, 1.0):
                    self.commit(pts, s, None, True)
                    break
        relax, fails, total = 1.0, 0, 0
        while len(self.edges) < n_edges:
            total += 1
            if total > 80000:
                raise RuntimeError("Could not place all distribution lines; try another seed.")
            if fails and fails % 200 == 0:
                relax = max(0.3, relax * 0.85)
            fails += 1
            weights = [1.0 / (1 + d) ** 2 for d in self.deg]
            s = rng.choices(range(len(self.nodes)), weights=weights)[0]
            if len(self.edges) > 20 and rng.random() < 0.12:
                cands = [j for j in range(len(self.nodes))
                         if j != s and frozenset((s, j)) not in self.adj
                         and 0.5 * self.scale <= math.dist(self.nodes[s], self.nodes[j]) <= 2.0 * self.scale]
                if not cands:
                    continue
                cands.sort(key=lambda j: (math.dist(self.nodes[s], self.nodes[j]), j))
                e = rng.choice(cands[:4])
                pts = self.route(self.nodes[s], self.nodes[e])
                if self.acceptable(pts, s, e, relax):
                    self.commit(pts, s, e, False)
                    fails = 0
                continue
            base = rng.choice(self.base[s])
            if rng.random() < 0.7:
                h = rot(base, rng.gauss(0, 0.45))
            else:
                h = rot(base, rng.choice([-1, 1]) * rng.uniform(0.9, 1.5))
            ln = self.scale * rng.uniform(0.55, 1.35) * max(0.5, relax)
            b = (self.nodes[s][0] + h[0] * ln, self.nodes[s][1] + h[1] * ln)
            if not self.inside(b) or not self.min_sep_ok(b, s, relax):
                continue
            pts = self.route(self.nodes[s], b)
            if self.acceptable(pts, s, None, relax):
                self.commit(pts, s, None, True)
                fails = 0

    def min_sep_ok(self, p, parent, relax):
        sep = self.sep0 * relax
        return all(math.dist(p, q) >= sep for i, q in enumerate(self.nodes) if i != parent)


# --------------------------------------------------------------------------- #
# main pipeline
# --------------------------------------------------------------------------- #
def build_network(input_path, seed=DEFAULT_SEED, id_field=None, type_field=None, tag_features=False):
    raw = Path(input_path).read_bytes()
    data = json.loads(raw)
    features = data["features"]
    id_field, type_field = detect_fields(features, id_field, type_field)

    def fid(f):
        return f["properties"][id_field]

    trunk_idx = sorted((i for i, f in enumerate(features) if "trunk" in str(f["properties"][type_field]).lower()),
                       key=lambda i: natural_key(fid(features[i])))
    dist_idx = sorted((i for i, f in enumerate(features) if i not in set(trunk_idx)),
                      key=lambda i: natural_key(fid(features[i])))
    if len(trunk_idx) != EXPECTED_TRUNKS:
        raise ValueError(f"Expected {EXPECTED_TRUNKS} trunk features, found {len(trunk_idx)}.")

    xs, ys = [], []
    for f in features:
        for c in iter_coords((f.get("geometry") or {}).get("coordinates", [])):
            xs.append(c[0])
            ys.append(c[1])
    bbox = (min(xs), min(ys), max(xs), max(ys))
    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        raise ValueError("Degenerate source extent.")
    proj = LocalProjection(bbox)
    x0, y0 = proj.fwd(bbox[0], bbox[1])
    x1, y1 = proj.fwd(bbox[2], bbox[3])
    box = (x0, y0, x1, y1)

    rng = random.Random(seed)
    trunks = build_trunks(rng, box)
    junctions = node_trunk_crossings(trunks)
    builder = Builder(rng, box, trunks, junctions)
    taps = builder.place_taps()
    builder.grow(taps, len(dist_idx))

    def to_lonlat(pts):
        out = []
        for x, y in pts:
            lon, lat = proj.inv(x, y)
            c = [round(min(max(lon, bbox[0]), bbox[2]), 6), round(min(max(lat, bbox[1]), bbox[3]), 6)]
            if not out or out[-1] != c:
                out.append(c)
        return out

    out = copy.deepcopy(data)
    for k, i in enumerate(trunk_idx):
        out["features"][i]["geometry"] = {"type": "LineString", "coordinates": to_lonlat(builder.trunks[k])}
    for k, i in enumerate(dist_idx):
        out["features"][i]["geometry"] = {"type": "LineString", "coordinates": to_lonlat(builder.lines[k])}
    if tag_features:
        for f in out["features"]:
            f["properties"]["geometry_note"] = "synthetic_illustrative"

    meta = {
        "geometry_type": "synthetic_illustrative",
        "disclaimer": DISCLAIMER,
        "generator": "scripts/generate_pipeline_network.py",
        "generator_version": GENERATOR_VERSION,
        "random_seed": seed,
        "source_file": Path(input_path).name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "coordinate_order": "[longitude, latitude], WGS84 (EPSG:4326)",
        "generation_parameters": {"id_field": id_field, "type_field": type_field, "tag_features": tag_features},
        "preserved": "feature order, pipeline IDs and all original properties; only geometry was replaced",
    }
    key = "metadata" if "metadata" not in out else "synthetic_geometry_metadata"
    out[key] = meta
    return out


def serialize(collection):
    return json.dumps(collection, indent=2, ensure_ascii=False) + "\n"


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", default=str(root / "data" / "chakan_pipelines.geojson"))
    ap.add_argument("--output", default=str(root / "data" / "chakan_pipelines_simulated.geojson"))
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--id-field")
    ap.add_argument("--type-field")
    ap.add_argument("--tag-features", action="store_true",
                    help="also add a 'geometry_note' property to every feature (off by default)")
    a = ap.parse_args(argv)

    src, dst = Path(a.input).resolve(), Path(a.output).resolve()
    if src == dst:
        sys.exit("Refusing to overwrite the input file.")
    result = build_network(src, a.seed, a.id_field, a.type_field, a.tag_features)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(serialize(result), encoding="utf-8")
    print(f"Wrote {len(result['features'])} features to {dst} (seed={a.seed})")


if __name__ == "__main__":
    main()