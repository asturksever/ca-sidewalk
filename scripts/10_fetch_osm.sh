#!/bin/zsh
# Download the Geofabrik Canada extract (~3.5 GB). Resumable.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw
curl -L -C - -o data/raw/canada-latest.osm.pbf \
  https://download.geofabrik.de/north-america/canada-latest.osm.pbf
ls -lh data/raw/canada-latest.osm.pbf
