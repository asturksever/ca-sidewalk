#!/usr/bin/env python3
"""Filter OSM Canada to the pedestrian network and normalize to the unified schema.

Input : data/raw/canada-latest.osm.pbf
Output: data/build/osm_ped.parquet  (EPSG:4326, unified schema)

v1 feature definition (separately-mapped pedestrian ways only):
  include highway in {footway, pedestrian, steps, path, living_street}
          minus path with foot=no
          plus  cycleway with foot in {yes, designated}
  exclude area=yes, indoor=yes, access=private
  (road-centerline sidewalk=left/right tags are a v2 item: geometry is the road,
   not the sidewalk, and would double-count against CPND's real geometries)

Run:  .venv/bin/python scripts/11_filter_osm.py
"""
from pathlib import Path

import duckdb
import quackosm

ROOT = Path(__file__).resolve().parents[1]
PBF = ROOT / "data/raw/canada-latest.osm.pbf"
OUT = ROOT / "data/build/osm_ped.parquet"

HIGHWAYS = ["footway", "pedestrian", "steps", "path", "living_street", "cycleway"]


def main():
    # QuackOSM streams the PBF through DuckDB with disk spill; laptop-safe.
    # keep_all_tags so the fine-grained rules below can inspect foot/area/etc.
    gpq = quackosm.convert_pbf_to_parquet(
        str(PBF),
        tags_filter={"highway": HIGHWAYS},
        keep_all_tags=True,
        ignore_cache=False,
    )
    print(f"quackosm wrote {gpq}")

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
    COPY (
      WITH src AS (
        SELECT
          feature_id,
          tags['highway'] AS highway,
          tags['footway'] AS footway,
          tags['foot'] AS foot,
          tags['name'] AS street,
          tags['surface'] AS material,
          tags['area'] AS area,
          tags['indoor'] AS indoor,
          tags['access'] AS access,
          geometry
        FROM read_parquet('{gpq}')
        WHERE ST_GeometryType(geometry) IN ('LINESTRING', 'MULTILINESTRING')
      )
      SELECT
        feature_id AS id,
        CASE
          WHEN footway = 'sidewalk' THEN 'sidewalk'
          WHEN footway = 'crossing' OR highway = 'crossing' THEN 'crossing'
          WHEN highway = 'steps' THEN 'steps'
          WHEN highway IN ('pedestrian', 'living_street') THEN 'pedestrian_street'
          WHEN highway IN ('path', 'cycleway') THEN 'path'
          WHEN highway = 'footway' THEN 'footway_other'
          ELSE 'other'
        END AS cls,
        highway AS osm_tag,
        street,
        material,
        geometry
      FROM src
      WHERE (area IS NULL OR area != 'yes')
        AND (indoor IS NULL OR indoor NOT IN ('yes', '1'))
        AND (access IS NULL OR access NOT IN ('private', 'no'))
        AND NOT (highway = 'path' AND foot = 'no')
        AND NOT (highway = 'cycleway' AND (foot IS NULL OR foot NOT IN ('yes', 'designated')))
    ) TO '{OUT}' (FORMAT parquet);
    """)
    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{OUT}')").fetchone()[0]
    print(f"wrote {n:,} rows -> {OUT}")
    for cls, c in con.execute(
        f"SELECT cls, COUNT(*) FROM read_parquet('{OUT}') GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall():
        print(f"  {cls:20s} {c:,}")


if __name__ == "__main__":
    main()
