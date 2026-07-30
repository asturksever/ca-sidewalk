#!/usr/bin/env python3
"""Extract the StatCan CPND GeoPackage into normalized GeoParquet.

Input : data/raw/EN/pedestrian_network.gpkg  (EPSG:3347, 1.71M MultiLineStrings)
Output: data/build/cpnd.parquet              (EPSG:4326 LineStrings, unified schema)

Run:  .venv/bin/python scripts/00_extract_cpnd.py
"""
from pathlib import Path

import pyogrio

ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "data/raw/EN/pedestrian_network.gpkg"
OUT = ROOT / "data/build/cpnd.parquet"

# StatCan standard_class -> unified cls vocabulary shared with the OSM side.
# Vocabulary: sidewalk | path | crossing | steps | bridge | pedestrian_street | other
CLS_MAP = {
    "Sidewalk": "sidewalk",
    "Pedestrian Path": "path",
    "Unpaved Path": "path",
    "Multi-use Path": "path",
    "Crosswalk": "crossing",
    "Stairway": "steps",
    "Bridge or Underpass": "bridge",
    "Pedestrian Zone": "pedestrian_street",
}

COLS = [
    "id", "standard_class", "material", "width", "street",
    "csduid", "csdname", "prov_terr",
]


def main():
    info = pyogrio.read_info(GPKG)
    print(f"layer={info['layer_name']} crs={info['crs']} features={info['features']:,}")

    gdf = pyogrio.read_dataframe(GPKG, columns=COLS, use_arrow=True)

    # ".." is StatCan's null token
    for c in ("material", "street", "csdname"):
        gdf[c] = gdf[c].replace("..", None)

    gdf["cls"] = gdf["standard_class"].map(CLS_MAP).fillna("other")
    unmapped = gdf.loc[~gdf["standard_class"].isin(CLS_MAP), "standard_class"].unique()
    if len(unmapped):
        print(f"WARNING unmapped classes -> 'other': {list(unmapped)}")

    gdf["prov"] = gdf["prov_terr"].str.upper()
    gdf = gdf.rename(columns={"csdname": "muni"})[
        ["id", "cls", "material", "width", "street", "muni", "csduid", "prov", "geometry"]
    ]

    gdf = gdf.explode(index_parts=False, ignore_index=True)
    gdf = gdf.to_crs(4326)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(OUT, write_covering_bbox=True)
    print(f"wrote {len(gdf):,} rows -> {OUT}")
    print(gdf["cls"].value_counts().to_string())


if __name__ == "__main__":
    main()
