#!/usr/bin/env bash
# Haalt een verkleinde kopie van de echte albums van de server op naar
# ./sample-photos, zodat je lokaal kunt bouwen zonder 1+ GB te downloaden.
# EXIF (datum, camera, lens) en notes.md blijven behouden.
#
#   ./tools/fetch-sample.sh            # alles, max 2400 px
#   MAX=1600 ./tools/fetch-sample.sh   # kleiner/sneller
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=${HOST:-ubuntu@makkers.net}
SRC=${SRC:-/mnt/storagebox/micktures}
MAX=${MAX:-2400}

echo "Verkleinde kopie maken op $HOST ..."
ssh "$HOST" "rm -rf /tmp/purrfolio-sample && mkdir -p /tmp/purrfolio-sample && python3 - '$SRC' /tmp/purrfolio-sample $MAX" <<'PY'
import sys, shutil
from pathlib import Path
from PIL import Image
src, dst, mx = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
for album in sorted(p for p in src.iterdir() if p.is_dir()):
    out = dst / album.name
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(album.iterdir()):
        if f.name.startswith(('.', '._')):
            continue
        if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
            with Image.open(f) as im:
                exif = im.info.get('exif')
                im.thumbnail((mx, mx))
                kw = {'quality': 86}
                if exif:
                    kw['exif'] = exif
                im.convert('RGB').save(out / f.name, 'JPEG', **kw)
        elif f.suffix.lower() in ('.md', '.txt'):
            shutil.copyfile(f, out / f.name)
    print(f'  {album.name}')
PY
echo "Ophalen ..."
rm -rf sample-photos
ssh "$HOST" "tar -C /tmp -cf - purrfolio-sample" | tar -xf - -C . && mv purrfolio-sample sample-photos
ssh "$HOST" "rm -rf /tmp/purrfolio-sample"
echo "Klaar: $(find sample-photos -type f | wc -l) bestanden, $(du -sh sample-photos | cut -f1)"
