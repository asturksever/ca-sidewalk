#!/usr/bin/env python3
"""Conflation quality stats: per-municipality match rates and national totals.

Run:  .venv/bin/python scripts/50_stats.py [path/to/unified.parquet]
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
UNIFIED = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/build/unified.parquet"

con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial;")

print("=== National provenance totals (km) ===")
print(con.execute(f"""
  SELECT provenance,
         COUNT(*) AS features,
         ROUND(SUM(ST_Length_Spheroid(ST_GeomFromWKB(geometry)))/1000, 1) AS km
  FROM read_parquet('{UNIFIED}')
  GROUP BY 1 ORDER BY 3 DESC
""").df().to_string(index=False))

print("\n=== Per-municipality CPND match rate (top 40 by km) ===")
print(con.execute(f"""
  WITH m AS (
    SELECT muni, prov, provenance,
           SUM(ST_Length_Spheroid(ST_GeomFromWKB(geometry)))/1000 AS km
    FROM read_parquet('{UNIFIED}')
    WHERE muni IS NOT NULL
    GROUP BY 1, 2, 3
  )
  SELECT muni, prov,
         ROUND(SUM(km), 1) AS cpnd_km,
         ROUND(100 * SUM(km) FILTER (provenance = 'both') / NULLIF(SUM(km), 0), 1)
           AS pct_both
  FROM m
  WHERE provenance IN ('both', 'statcan_only')
  GROUP BY 1, 2 ORDER BY cpnd_km DESC LIMIT 40
""").df().to_string(index=False))

print("\nSanity: pct_both 40-85 plausible; <20 suggests CRS/threshold bug; "
      ">95 suggests over-matching.")
