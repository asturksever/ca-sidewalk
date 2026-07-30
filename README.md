# Sidewalks of Canada 🍁

A national map of Canada's pedestrian network, conflating two sources into one
unified, provenance-tagged dataset:

- **Statistics Canada — Canadian Pedestrian Network Database (CPND, 2025)**,
  catalogue 34-26-0004: 1.71 M segments aggregated from 68 municipal open-data
  sources across 158 census subdivisions.
- **OpenStreetMap** (Geofabrik Canada extract): all separately-mapped
  pedestrian ways nationwide.

Every segment carries `provenance`:

| value | meaning | colour |
|---|---|---|
| `both` | geometry confirmed by both sources | maple red `#D80621` |
| `statcan_only` | in CPND but not matched in OSM | blue `#1D63C8` |
| `osm_only` | in OSM but not in CPND (or outside CPND coverage) | amber `#E39B00` |

The app is Vite + MapLibre GL, styled "maple red & winter white", serving a
single national PMTiles archive with HTTP range requests — no tile server.

## Pipeline

All scripts live in `scripts/`, run with the project venv
(`uv venv && uv pip install -e .` or `uv sync`):

| step | script | output |
|---|---|---|
| 0 | `00_extract_cpnd.py` | `data/build/cpnd.parquet` (unified schema, EPSG:4326) |
| 1 | `10_fetch_osm.sh` | `data/raw/canada-latest.osm.pbf` |
| 2 | `11_filter_osm.py` | `data/build/osm_ped.parquet` (QuackOSM + DuckDB rules) |
| 3 | `30_conflate.py` | `data/build/unified.parquet` — per-CSD buffer+azimuth matching (EPSG:3347, 25 m edges, 10 m buffer, ≥60 % overlap, ≤25° azimuth); CPND geometry canonical, matched OSM dropped |
| 4 | `45_dev_sample.py` | small GeoJSON for local dev without tiles |
| 5 | `50_stats.py` | per-municipality match-rate report |
| 6 | `60_gen_attribution.py` | `src/attributions.json` for the sources modal |

Tiling runs in CI (`.github/workflows/build-tiles.yml`) because tippecanoe
can't execute on the dev machine: upload `unified.parquet` as a release asset
(`data-v1`), dispatch the workflow, and it attaches
`canada_sidewalks.pmtiles` to the `tiles-v1` release. The Pages deploy
workflow bundles those tiles into the site so they're served same-origin.

## Local dev

```
npm install
npm run dev   # port 5175; falls back to public/data/dev_sample.geojson if no tiles
```

## OSM feature definition (v1)

`highway ∈ {footway, pedestrian, steps, path, living_street}` (minus
`path` + `foot=no`) plus `cycleway` with `foot ∈ {yes, designated}`;
excluding `area=yes`, `indoor=yes`, `access ∈ {private, no}`. Road-centreline
`sidewalk=left/right/both` tags are deliberately excluded (the geometry is the
road, not the sidewalk) — a v2 candidate.

## Licences

See the "Data sources" modal in the app: StatCan Open Licence, ODbL for OSM,
plus per-municipality statements from the CPND `data_sources.csv`.
