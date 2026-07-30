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
     OSM edge matched  -> dropped (dedupe); unmatched -> 'osm_only'
  5. line_merge contiguous same-provenance runs per parent feature
OSM features never touching a CPND CSD bbox pass through untouched as osm_only.

Run:  .venv/bin/python scripts/30_conflate.py [--sample TORONTO|CALGARY|MONCTON]
"""
import argparse
import sys
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

# Matching parameters — tuned on Toronto / Calgary / Moncton samples
SEG_M = 25.0          # max vertex spacing before edge explosion
BUFFER_M = 10.0       # CPND edge buffer for overlap test
DWITHIN_M = 12.0      # candidate search distance
MIN_OVERLAP = 0.6     # fraction of OSM edge length inside CPND buffer
MAX_AZ_DEG = 25.0     # max azimuth difference (mod 180)
BBOX_PAD_DEG = 0.006  # ~500 m pad around each CSD bbox at Canadian latitudes

METRIC_CRS = 3347     # NAD83 / Statistics Canada Lambert

SAMPLES = {  # csduid prefixes for tuning runs
    "TORONTO": ["3520005"],
    "CALGARY": ["4806016"],
    "MONCTON": ["1307022"],
}


def explode_edges(geoms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Explode segmentized lines into 2-point edges. Returns (edges, parent_idx)."""
    seg = shapely.segmentize(geoms, SEG_M)
    coords, idx = shapely.get_coordinates(seg, return_index=True)
    # consecutive coordinate pairs within the same parent feature
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
    az = np.degrees(np.arctan2(d[:, 0], d[:, 1]))  # from north
    return np.mod(az, 180.0)


def match_chunk(cpnd: gpd.GeoDataFrame, osm: gpd.GeoDataFrame):
    """Conflate one CSD chunk (both frames in METRIC_CRS).

    Returns (cpnd_edges_df, osm_edges_df) with edge geometry, parent row index
    and a 'matched' bool per edge.
    """
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
                # overlap test only on azimuth-passing pairs
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
    osm_used_ids: set = set()

    for n, csduid in enumerate(csduids, 1):
        c = cpnd[cpnd["csduid"] == csduid]
        minx, miny, maxx, maxy = c.total_bounds
        bbox = (minx - BBOX_PAD_DEG, miny - BBOX_PAD_DEG,
                maxx + BBOX_PAD_DEG, maxy + BBOX_PAD_DEG)
        o = gpd.read_parquet(OSM, bbox=bbox)
        o = o[~o["id"].isin(osm_used_ids)]
        osm_used_ids.update(o["id"])

        cm = c.to_crs(METRIC_CRS)
        om = o.to_crs(METRIC_CRS)

        (c_edges, c_par, c_hit), (o_edges, o_par, o_hit) = match_chunk(cm, om)

        cpnd_out = reassemble(
            c_edges, c_par, c_hit, cm,
            {True: "both", False: "statcan_only"},
            ["cls", "material", "width", "street", "muni", "prov"],
        )
        # matched OSM edges are dropped; unmatched become osm_only
        osm_keep = ~o_hit
        osm_out = reassemble(
            o_edges[osm_keep], o_par[osm_keep], np.zeros(osm_keep.sum(), dtype=bool), om,
            {False: "osm_only", True: "osm_only"},
            ["cls", "material", "street", "osm_tag"],
        )
        chunk = gpd.GeoDataFrame(cpnd_out + osm_out, crs=METRIC_CRS).to_crs(4326)
        results.append(chunk)
        pct = 100 * c_hit.mean() if len(c_hit) else 0
        print(f"[{n}/{len(csduids)}] {csduid} ({c['muni'].iloc[0]}): "
              f"cpnd_edges={len(c_hit):,} osm_edges={len(o_hit):,} "
              f"cpnd_matched={pct:.1f}%", flush=True)

    if not args.sample:
        # everything OSM not consumed by any chunk passes through untouched
        osm_all = gpd.read_parquet(OSM)
        rest = osm_all[~osm_all["id"].isin(osm_used_ids)].copy()
        rest["provenance"] = "osm_only"
        rest = rest[["provenance", "cls", "material", "street", "osm_tag", "geometry"]]
        results.append(rest)
        print(f"osm passthrough outside CPND munis: {len(rest):,} rows")

    unified = gpd.GeoDataFrame(pd.concat(results, ignore_index=True), crs=4326)
    unified = unified[~unified.geometry.is_empty & unified.geometry.notna()]
    out = OUT if not args.sample else OUT.with_name(f"unified_{args.sample.lower()}.parquet")
    unified.to_parquet(out, write_covering_bbox=True)
    print(f"wrote {len(unified):,} rows -> {out}")
    print(unified["provenance"].value_counts().to_string())


if __name__ == "__main__":
    main()
