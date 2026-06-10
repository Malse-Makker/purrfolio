#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.env" ]; then
  while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    line="${line//\"/}"
    line="${line//\'/}"
    export "$line"
  done < "$SCRIPT_DIR/.env"
fi

PHOTOS_DIR="${PHOTOS_DIR:-$SCRIPT_DIR/photos}"
OUTPUT_DIR="$SCRIPT_DIR/output"

echo ""
echo "  Purrfolio builder"
echo "  Photos : $PHOTOS_DIR"
echo "  Output : $OUTPUT_DIR"
echo ""

mkdir -p \
  "$OUTPUT_DIR" \
  "$OUTPUT_DIR/albums" \
  "$OUTPUT_DIR/photos" \
  "$OUTPUT_DIR/previews" \
  "$OUTPUT_DIR/thumbs"

docker build -t purrfolio-builder "$SCRIPT_DIR" -q

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PHOTOS_DIR":/photos:ro \
  -v "$OUTPUT_DIR":/output \
  -v "$SCRIPT_DIR/context":/app/context:ro \
  -v "$SCRIPT_DIR/VERSION":/app/VERSION:ro \
  -e PHOTOS_DIR=/photos \
  -e OUTPUT_DIR=/output \
  -e CONTEXT_DIR=/app/context \
  -e "SITE_TITLE=${SITE_TITLE:-My Portfolio}" \
  -e "SITE_AUTHOR=${SITE_AUTHOR:-Photographer}" \
  -e "INSTAGRAM_URL=${INSTAGRAM_URL:-}" \
  purrfolio-builder

echo "  Done."
echo ""
