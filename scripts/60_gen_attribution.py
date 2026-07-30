#!/usr/bin/env python3
"""Generate src/attributions.json from the CPND data_sources.csv.

Run:  .venv/bin/python scripts/60_gen_attribution.py
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data/raw/EN/data_sources.csv"
OUT = ROOT / "src/attributions.json"

PROV_NAMES = {
    "ab": "Alberta", "bc": "British Columbia", "mb": "Manitoba",
    "nb": "New Brunswick", "nl": "Newfoundland and Labrador",
    "ns": "Nova Scotia", "nt": "Northwest Territories", "nu": "Nunavut",
    "on": "Ontario", "pe": "Prince Edward Island", "qc": "Quebec",
    "sk": "Saskatchewan", "yt": "Yukon",
}

by_prov = defaultdict(list)
seen = set()
with open(CSV, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        prov = PROV_NAMES.get(row["prov_terr"].strip().lower(), row["prov_terr"])
        muni = row["municipality"].strip().title()
        key = (prov, muni, row["attribution_statement"].strip())
        if key in seen:
            continue
        seen.add(key)
        by_prov[prov].append({
            "municipality": muni,
            "statement": row["attribution_statement"].strip(),
            "source_url": row["source_url"].strip(),
            "licence_url": row["licence_url"].strip(),
            "last_update": row["last_update"].strip(),
        })

out = {
    "national": [
        {
            "name": "Statistics Canada — Canadian Pedestrian Network Database (2025)",
            "statement": "Source: Statistics Canada, Canadian Pedestrian Network Database, "
                         "Catalogue 34-26-0004, 2025. Reproduced and distributed on an "
                         "\"as is\" basis with the permission of Statistics Canada.",
            "licence_url": "https://www.statcan.gc.ca/en/reference/licence",
            "source_url": "https://www150.statcan.gc.ca/n1/pub/34-26-0004/342600042025001-eng.htm",
        },
        {
            "name": "OpenStreetMap",
            "statement": "© OpenStreetMap contributors, licensed under the Open Database Licence (ODbL).",
            "licence_url": "https://www.openstreetmap.org/copyright",
            "source_url": "https://www.openstreetmap.org",
        },
        {
            "name": "OpenFreeMap / OpenMapTiles (basemap)",
            "statement": "Basemap tiles by OpenFreeMap, schema © OpenMapTiles, data © OpenStreetMap contributors.",
            "licence_url": "https://openfreemap.org",
            "source_url": "https://openfreemap.org",
        },
    ],
    "municipal": {p: sorted(v, key=lambda r: r["municipality"])
                  for p, v in sorted(by_prov.items())},
}

OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
n = sum(len(v) for v in by_prov.values())
print(f"wrote {n} municipal statements across {len(by_prov)} provinces -> {OUT}")
