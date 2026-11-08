#!/usr/bin/env python3
"""Validate data/chakan_pipelines_simulated.geojson against the original.

Usage:  python scripts/validate_pipeline_network.py [--original P] [--simulated P]
Exit code 0 = all checks passed, 1 = at least one failed.
Also importable: validate(original_path, simulated_path) -> list of failure strings.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString

TOL = 1e-7  # degrees (~1 cm)
HERE = Path(__file__).resolve().parent


def _coords(c):
    if c and isinstance(c[0], (int, float)):
        yield c
    else:
        for x in c:
            yield from _coords(x)


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_pipeline_network", HERE / "generate_pipeline_network.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_checks(original_path, simulated_path, check_determinism=True):
    results = []

    def rec(name, errors):
        results.append((name, not errors, "; ".join(errors[:5]) + (f" (+{len(errors)-5} more)" if len(errors) > 5 else "")))

    raw_o = Path(original_path).read_bytes()
    raw_s = Path(simulated_path).read_text(encoding="utf-8")
    orig, sim = json.loads(raw_o), json.loads(raw_s)
    fo, fs = orig["features"], sim["features"]

    rec("exactly 132 features", [] if len(fs) == 132 else [f"found {len(fs)}"])

    meta = sim.get("metadata") or sim.get("synthetic_geometry_metadata") or {}
    gp = meta.get("generation_parameters", {})
    id_field = gp.get("id_field", "pipeline_id")
    ids_o = [f["properties"].get(id_field) for f in fo]
    ids_s = [f["properties"].get(id_field) for f in fs]
    errs = []
    if len(set(ids_s)) != len(ids_s):
        errs.append("duplicate IDs")
    if sorted(map(str, ids_o)) != sorted(map(str, ids_s)):
        errs.append("ID sets differ")
    if ids_o != ids_s:
        errs.append("feature order differs")
    rec("all original IDs retained exactly once", errs)

    errs = []
    for a, b in zip(fo, fs):
        pa, pb = a.get("properties", {}), b.get("properties", {})
        for k, v in pa.items():
            if k not in pb or pb[k] != v:
                errs.append(f"{pa.get(id_field)}: property '{k}' changed")
        extra = set(pb) - set(pa) - {"geometry_note"}
        if extra:
            errs.append(f"{pa.get(id_field)}: unexpected new properties {sorted(extra)}")
    rec("all original properties retained", errs)

    errs, lines = [], []
    for f in fs:
        g = f.get("geometry")
        if not g or g.get("type") != "LineString":
            errs.append(f"{f['properties'].get(id_field)}: not a LineString")
            lines.append(None)
            continue
        ls = LineString(g["coordinates"])
        if ls.is_empty or not ls.is_valid or len(g["coordinates"]) < 2 or ls.length == 0:
            errs.append(f"{f['properties'].get(id_field)}: empty/invalid")
        lines.append(ls)
    rec("geometries are valid, non-empty LineStrings", errs)
    if any(l is None for l in lines):
        return results

    xs, ys = [], []
    for f in fo:
        for c in _coords((f.get("geometry") or {}).get("coordinates", [])):
            xs.append(c[0]); ys.append(c[1])
    bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
    errs = []
    for f, l in zip(fs, lines):
        for x, y in l.coords:
            if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
                errs.append(f"{f['properties'].get(id_field)}: bad lon/lat")
            elif not (bx0 - 1e-9 <= x <= bx1 + 1e-9 and by0 - 1e-9 <= y <= by1 + 1e-9):
                errs.append(f"{f['properties'].get(id_field)}: outside monitoring area")
    sx = [c[0] for l in lines for c in l.coords]; sy = [c[1] for l in lines for c in l.coords]
    cover = ((max(sx) - min(sx)) / (bx1 - bx0), (max(sy) - min(sy)) / (by1 - by0))
    if min(cover) < 0.9:
        errs.append(f"extent covers only {cover[0]:.0%} x {cover[1]:.0%} of the original")
    rec("coordinates in lon/lat order, inside original extent (>=90% covered)", errs)

    # topology: shared vertices, no stray crossings, single connected network
    n = len(lines)
    verts = [set(map(tuple, l.coords)) for l in lines]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    errs = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = lines[i], lines[j]
            if a.bounds[0] > b.bounds[2] + TOL or b.bounds[0] > a.bounds[2] + TOL or \
               a.bounds[1] > b.bounds[3] + TOL or b.bounds[1] > a.bounds[3] + TOL:
                continue
            if a.distance(b) > TOL:
                continue
            parent[find(i)] = find(j)
            inter = a.intersection(b)
            for g in getattr(inter, "geoms", [inter]):
                if g.geom_type != "Point":
                    errs.append(f"{ids_s[i]}/{ids_s[j]} overlap along a segment")
                    continue
                p = (g.x, g.y)
                near = lambda vs: any(abs(p[0] - v[0]) < TOL and abs(p[1] - v[1]) < TOL for v in vs)
                if not (near(verts[i]) and near(verts[j])):
                    errs.append(f"{ids_s[i]}/{ids_s[j]} cross/touch away from a shared junction vertex")
    rec("no stray crossings; lines meet only at shared junction vertices", errs)

    comps = len({find(i) for i in range(n)})
    rec("network is a single connected component", [] if comps == 1 else [f"{comps} components"])

    ttype = gp.get("type_field", "pipeline_type")
    errs = []
    for i, f in enumerate(fs):
        if "trunk" in str(f["properties"].get(ttype, "")).lower():
            continue
        ends = [tuple(lines[i].coords[0]), tuple(lines[i].coords[-1])]
        others = set().union(*(verts[j] for j in range(n) if j != i))
        if not any(any(abs(e[0] - v[0]) < TOL and abs(e[1] - v[1]) < TOL for v in others) for e in ends):
            errs.append(f"{ids_s[i]}: no endpoint on another pipeline")
    rec("every distribution line has an endpoint on another pipeline", errs)

    errs = []
    for f, l in zip(fs, lines):
        if "trunk" in str(f["properties"].get(ttype, "")).lower() and len(l.coords) < 8:
            errs.append(f"{f['properties'].get(id_field)}: only {len(l.coords)-2} interior bends")
    rec("trunks are irregular (>= 6 interior vertices each)", errs)

    k = math.cos(math.radians((by0 + by1) / 2))
    tot = axis = 0.0
    for l in lines:
        c = list(l.coords)
        for (x0, y0), (x1, y1) in zip(c, c[1:]):
            dx, dy = (x1 - x0) * k, y1 - y0
            ln = math.hypot(dx, dy)
            ang = math.degrees(math.atan2(abs(dy), abs(dx)))
            tot += ln
            if ang < 3 or ang > 87:
                axis += ln
    frac = axis / tot
    rec("not grid-like (<15% of length within 3 deg of an axis)", [] if frac < 0.15 else [f"{frac:.0%} axis-aligned"])

    errs = []
    if meta.get("geometry_type") != "synthetic_illustrative" or "illustrative" not in meta.get("disclaimer", ""):
        errs.append("synthetic/illustrative metadata missing")
    if meta.get("source_sha256") != hashlib.sha256(raw_o).hexdigest():
        errs.append("original file differs from the one the output was generated from")
    rec("synthetic metadata present; original file unchanged since generation", errs)

    if check_determinism:
        gen = _load_generator()
        args = (original_path, meta.get("random_seed", 42), gp.get("id_field"), gp.get("type_field"),
                gp.get("tag_features", False))
        a, b = gen.serialize(gen.build_network(*args)), gen.serialize(gen.build_network(*args))
        errs = []
        if a != b:
            errs.append("two runs differ")
        if a != raw_s:
            errs.append("regenerated output differs from the saved file")
        rec("deterministic (two fresh runs identical and match saved file)", errs)
    return results


def validate(original_path, simulated_path, check_determinism=True):
    return [f"{n}: {d}" for n, ok, d in run_checks(original_path, simulated_path, check_determinism) if not ok]


def main(argv=None):
    root = HERE.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", default=str(root / "data" / "chakan_pipelines.geojson"))
    ap.add_argument("--simulated", default=str(root / "data" / "chakan_pipelines_simulated.geojson"))
    ap.add_argument("--skip-determinism", action="store_true")
    a = ap.parse_args(argv)
    results = run_checks(a.original, a.simulated, not a.skip_determinism)
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results)-failed}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
