#!/usr/bin/env bash
# Bouw de site lokaal en bekijk hem in je browser.
#
#   ./preview.sh                 # bouw uit ./sample-photos en serveer op :8090
#   PORT=9000 ./preview.sh
#   PHOTOS_DIR=~/fotos ./preview.sh
#
# Nog geen sample-photos? Eerst: ./tools/fetch-sample.sh
set -euo pipefail
cd "$(dirname "$0")"

export PHOTOS_DIR="${PHOTOS_DIR:-$PWD/sample-photos}"
export OUTPUT_DIR="${OUTPUT_DIR:-$PWD/preview-output}"
export CONTEXT_DIR="$PWD/context"
export SITE_TITLE="${SITE_TITLE:-Micktures}"
export SITE_AUTHOR="${SITE_AUTHOR:-Mick}"
export INSTAGRAM_URL="${INSTAGRAM_URL:-https://www.instagram.com/micktures_/}"
PORT="${PORT:-8090}"

if [ ! -d "$PHOTOS_DIR" ]; then
  echo "Geen foto's in $PHOTOS_DIR. Draai eerst ./tools/fetch-sample.sh" >&2
  exit 1
fi

# Python met Pillow: gewoon, via nix-shell, of via de Docker-image
if python3 -c "import PIL" 2>/dev/null; then
  python3 build.py
elif command -v nix-shell >/dev/null; then
  nix-shell -p "python3.withPackages (p: [ p.pillow ])" --run "python3 build.py"
elif command -v docker >/dev/null; then
  docker build -q -t purrfolio-builder . >/dev/null
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$PHOTOS_DIR":/photos:ro -v "$OUTPUT_DIR":/output -v "$CONTEXT_DIR":/app/context:ro \
    -e SITE_TITLE -e SITE_AUTHOR -e INSTAGRAM_URL purrfolio-builder
else
  echo "Geen Python met Pillow, nix-shell of Docker gevonden." >&2
  exit 1
fi

echo "Bekijk: http://localhost:$PORT   (Ctrl+C om te stoppen)"
cd "$OUTPUT_DIR" && exec python3 -m http.server "$PORT" --bind 127.0.0.1
