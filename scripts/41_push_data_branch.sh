#!/bin/zsh
# Push data/build/unified.parquet to the `data` branch as <100 MB chunks.
# Pushing that branch triggers .github/workflows/build-tiles.yml, which
# reassembles the file, runs tippecanoe, and attaches canada_sidewalks.pmtiles
# to the tiles-v1 release.
set -euo pipefail
cd "$(dirname "$0")/.."

SRC=data/build/unified.parquet
[ -f "$SRC" ] || { echo "missing $SRC — run 30_conflate.py first"; exit 1; }

git branch -f data main
git switch data
rm -rf data-chunks && mkdir data-chunks
split -b 95m "$SRC" data-chunks/unified.parquet.part-
ls -lh data-chunks/
# .gitignore excludes data/ but data-chunks/ is intentionally tracked
git add -f data-chunks
git commit -m "Data drop: unified.parquet ($(date +%Y-%m-%d)) in 95MB chunks"
git push -f origin data
git switch main
echo "Pushed. Watch the 'Build PMTiles' workflow on GitHub."
