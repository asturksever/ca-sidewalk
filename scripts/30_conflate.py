#!/usr/bin/env python3
"""Conflate CPND and OSM pedestrian networks into one unified, provenance-tagged network.

Inputs : data/build/cpnd.parquet     (EPSG:4326, only ~158 CSDs have data)
         data/build/osm_ped.parquet  (EPSG:4326, all of Canada)
Output : data/build/unified.parquet  (EPSG:4326)
         provenance: both | statcan_only | osm_only

Method (per CSD chunk, in EPSG:3347 metres):
  1. segmentize both sides to <=SEG_M vertex spacing, explode into 2-point edges
  2. STRtree dwithin(DWITHIN_M) candidate pairs
  3. match if len(intersection(osm_edge, buffer(cpnd_edge, BUFFER_M))) / len(osm_edge)
     >= MIN_OVERLAP  AND  azimuth delta (mod 180) <= MAX_AZ_DEG
  4. CPND edge matched -> 'both'; unmatched -> 'statcan_only'
  5. line_merge contiguous same-provenance runs per parent feature

OSM handling across chunks: CSD bboxes overlap (e.g. the rural municipality
around Regina fully contains Regina), so an OSM feature may participate in
SEVERAL chunks' matching. Matched-edge flags are OR-merged per feature id
globally; a single final pass emits each feature's unmatched edges once as
osm_only. OSM features never touched by any chunk pass through untouched.
Edge explosion is deterministic per geometry, so per-chunk edge indices align.

Run:  .venv/bin/python scripts/30_conflate.py [--sample TORONTO|EDMONTON|MONCTON]
"""
import argparse
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import STRtree

ROOT = Path(__file__).resolve().parents[1]
CPND = ROOT / "data/build/cpnd.parquet"
OSM = ROOT / "data/build/osm_ped.parquet"
OUT = ROOT / "data/build/unified.parquet"

# Matching parameters — tuned on Toronto / Edmonton / Moncton samples
SEG_M = 25.0          # max vertex spacing before edge explosion
BUFFER_M = 10.0       # CPND edge buffer for overlap test
DWITHIN_M = 12.0      # candidate search distance
MIN_OVERLAP = 0.6     # fraction of OSM edge length inside CPND buffer
MAX_AZ_DEG = 25.0     # max azimuth difference (mod 180)
BBOX_PAD_DEG = 0.006  # ~500 m pad around each CSD bbox at Canadian latitudes

METRIC_CRS = 3347     # NAD83 / Statistics Canada Lambert

SAMPLES = {  # csduid prefixes for tuning runs (Calgary is not in CPND)
    "TORONTO": ["3520005"],
    "EDMONTON": ["4811061"],
    "MONCTON": ["1307022"],
}

OSM_KEEP = ["cls", "material", "street", "osm_tag"]
CPND_KEEP = ["cls", "material", "width", "street", "muni", "prov"]


def explode_edges(geoms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Explode segmentized lines into 2-point edges. Returns (edges, parent_idx)."""
    seg = shapely.segmentize(geoms, SEG_M)
    coords, idx = shapely.get_coordinates(seg, return_index=True)
    same = idx[:-1] == idx[1:]
    starts = coords[:-1][same]
    ends = coords[1:][same]
    parents = idx[:-1][same]
    pairs = np.stack([starts, ends], axis=1)  # (n, 2, 2)
    edges = shapely.linestrings(pairs)
    return edges, parents


def azimuths(edges_coords: np.ndarray) -> np.ndarray:
    """Azimuth in degrees [0, 180) for (n, 2, 2) coordinate pairs."""
    d = edges_coords[:, 1, :] - edges_coords[:, 0, :]
    az = np.degrees(np.arctan2(d[:, 0], d[:, 1]))
    return np.mod(az, 180.0)


def match_chunk(cpnd: gpd.GeoDataFrame, osm: gpd.GeoDataFrame):
    """Conflate one CSD chunk (both frames in METRIC_CRS)."""
    c_edges, c_parent = explode_edges(cpnd.geometry.values)
    o_edges, o_parent = explode_edges(osm.geometry.values)

    c_matched = np.zeros(len(c_edges), dtype=bool)
    o_matched = np.zeros(len(o_edges), dtype=bool)

    if len(c_edges) and len(o_edges):
        tree = STRtree(c_edges)
        oi, ci = tree.query(o_edges, predicate="dwithin", distance=DWITHIN_M)
        if len(oi):
            c_az = azimuths(shapely.get_coordinates(c_edges).reshape(-1, 2, 2))
            o_az = azimuths(shapely.get_coordinates(o_edges).reshape(-1, 2, 2))
            d_az = np.abs(c_az[ci] - o_az[oi])
            d_az = np.minimum(d_az, 180.0 - d_az)
            ok_az = d_az <= MAX_AZ_DEG

            oi, ci = oi[ok_az], ci[ok_az]
            if len(oi):
                bufs = shapely.buffer(c_edges[ci], BUFFER_M, cap_style="flat")
                inter = shapely.intersection(o_edges[oi], bufs)
                frac = shapely.length(inter) / np.maximum(shapely.length(o_edges[oi]), 1e-9)
                ok = frac >= MIN_OVERLAP
                o_matched[oi[ok]] = True
                c_matched[ci[ok]] = True

    return (c_edges, c_parent, c_matched), (o_edges, o_parent, o_matched)


def reassemble(edges, parents, matched, src_gdf, provenance_map, keep_cols):
    """Group edges by (parent, matched-state), line_merge, attach parent attrs."""
    out = []
    attrs = {c: src_gdf[c].values for c in keep_cols}
    df = pd.DataFrame({"parent": parents, "matched": matched, "edge": edges})
    for (parent, is_matched), grp in df.groupby(["parent", "matched"], sort=False):
        merged = shapely.line_merge(shapely.multilinestrings(grp["edge"].values))
        rec = {c: attrs[c][parent] for c in keep_cols}
        rec["provenance"] = provenance_map[bool(is_matched)]
        rec["geometry"] = merged
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", choices=SAMPLES.keys())
    args = ap.parse_args()

    cpnd = gpd.read_parquet(CPND)
    print(f"cpnd: {len(cpnd):,} rows")

    csduids = sorted(cpnd["csduid"].unique())
    if args.sample:
        csduids = [c for c in csduids if any(c.startswith(p) for p in SAMPLES[args.sample])]
        print(f"sample {args.sample}: csduids={csduids}")

    results = []
    # feature id -> OR-merged matched-edge flags (aligned across chunks because
    # edge explosion is deterministic per geometry)
    osm_edge_hits: dict = {}

    for n, csduid in enumerate(csduids, 1):
        c = cpnd[cpnd["csduid"] == csduid]
        minx, miny, maxx, maxy = c.total_bounds
        bbox = (minx - BBOX_PAD_DEG, miny - BBOX_PAD_DEG,
                maxx + BBOX_PAD_DEG, maxy + BBOX_PAD_DEG)
        o = gpd.read_parquet(OSM, bbox=bbox)

        cm = c.to_crs(METRIC_CRS)
        om = o.to_crs(METRIC_CRS)

        (c_edges, c_par, c_hit), (o_edges, o_par, o_hit) = match_chunk(cm, om)

        results.extend(reassemble(
            c_edges, c_par, c_hit, cm,
            {True: "both", False: "statcan_only"},
            CPND_KEEP,
        ))

        # OR-merge this chunk's OSM matched flags into the global accumulator
        ids = o["id"].values
        for parent in range(len(o)):
            mask = o_par == parent
            if not mask.any():
                continue
            hits = o_hit[mask]
            fid = ids[parent]
            prev = osm_edge_hits.get(fid)
            osm_edge_hits[fid] = hits if prev is None else (prev | hits)

        pct = 100 * c_hit.mean() if len(c_hit) else 0
        print(f"[{n}/{len(csduids)}] {csduid} ({c['muni'].iloc[0]}): "
              f"cpnd_edges={len(c_hit):,} osm_edges={len(o_hit):,} "
              f"cpnd_matched={pct:.1f}%", flush=True)

    # Final OSM pass: emit each touched feature's unmatched edges exactly once;
    # untouched features pass through with original geometry.
    osm_all = gpd.read_parquet(OSM)
    touched_mask = osm_all["id"].isin(osm_edge_hits.keys())
    untouched = osm_all[~touched_mask].copy()
    untouched["provenance"] = "osm_only"
    results_osm = untouched[["provenance", *OSM_KEEP, "geometry"]]

    touched = osm_all[touched_mask]
    if len(touched):
        tm = touched.to_crs(METRIC_CRS)
        t_edges, t_par = explode_edges(tm.geometry.values)
        ids = tm["id"].values
        keep = np.zeros(len(t_edges), dtype=bool)
        for parent in range(len(tm)):
            mask = t_par == parent
            hits = osm_edge_hits[ids[parent]]
            k = ~hits
            # guard against pathological length mismatch
            if len(k) == mask.sum():
                keep[mask] = k
            else:
                keep[mask] = True
        recs = reassemble(
            t_edges[keep], t_par[keep], np.zeros(int(keep.sum()), dtype=bool), tm,
            {False: "osm_only", True: "osm_only"},
            OSM_KEEP,
        )
        touched_out = gpd.GeoDataFrame(recs, crs=METRIC_CRS).to_crs(4326)
        print(f"osm touched by chunks: {len(touched):,} features -> "
              f"{len(touched_out):,} osm_only remnants")
    else:
        touched_out = gpd.GeoDataFrame(columns=["provenance", *OSM_KEEP, "geometry"],
                                       crs=4326)

    cpnd_out = gpd.GeoDataFrame(results, crs=METRIC_CRS).to_crs(4326)
    parts = [cpnd_out, touched_out]
    if not args.sample:
        parts.append(results_osm)
        print(f"osm passthrough outside CPND munis: {len(results_osm):,} rows")

    unified = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=4326)
    unified = unified[unified.geometry.notna() & ~unified.geometry.is_empty]
    out = OUT if not args.sample else OUT.with_name(f"unified_{args.sample.lower()}.parquet")
    unified.to_parquet(out, write_covering_bbox=True)
    print(f"wrote {len(unified):,} rows -> {out}")
    print(unified["provenance"].value_counts().to_string())


if __name__ == "__main__":
    main()
