#!/usr/bin/env python3
"""Cut a small city-scale GeoJSON sample for local dev when PMTiles aren't built yet.

Uses unified.parquet if present, else cpnd.parquet (provenance=statcan_only).
Default area: downtown Moncton, NB.

Run:  .venv/bin/python scripts/45_dev_sample.py
"""
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "data/build/unified.parquet"
CPND = ROOT / "data/build/cpnd.parquet"
OUT = ROOT / "public/data/dev_sample.geojson"

BBOX = (-64.85, 46.06, -64.72, 46.13)  # Moncton

src = UNIFIED if UNIFIED.exists() else CPND
gdf = gpd.read_parquet(src, bbox=BBOX)
gdf = gdf.cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]]
if "provenance" not in gdf.columns:
    gdf["provenance"] = "statcan_only"
keep = [c for c in ("provenance", "cls", "material", "width", "street", "muni", "prov",
                    "osm_tag") if c in gdf.columns]
gdf = gdf[keep + ["geometry"]]
OUT.parent.mkdir(parents=True, exist_ok=True)
gdf.to_file(OUT, driver="GeoJSON")
print(f"wrote {len(gdf):,} features from {src.name} -> {OUT}")
