#!/usr/bin/env python3
"""
Purrfolio - static photo portfolio generator.

Scans PHOTOS_DIR (one subfolder per album) and writes a static site to
OUTPUT_DIR. Re-running is cheap: resized images and EXIF data are cached and
only regenerated when the source photo changes.

Album folder contract (unchanged, SwipeShot exports rely on it):
  - images in the album folder, sorted by filename (001-..., 002-...)
  - cover.jpg (or any file starting with "cover") is the album cover and is
    not shown in the album itself
  - optional notes.md with text plus meta lines:
        date: 14-10-2026
        camera: Nikon Z6 II
        thumb_position: top|center|bottom|left|right
        title: Display name (default: folder name, dashes become spaces)
"""

import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps

# --- Configuration -----------------------------------------------------------

PHOTOS_DIR    = Path(os.environ.get("PHOTOS_DIR", "./photos"))
OUTPUT_DIR    = Path(os.environ.get("OUTPUT_DIR", "./output"))
CONTEXT_DIR   = Path(os.environ.get("CONTEXT_DIR", "./context"))
STATIC_DIR    = Path(os.environ.get("STATIC_DIR", Path(__file__).parent / "static"))
SITE_TITLE    = escape(os.environ.get("SITE_TITLE", "My Portfolio"))
SITE_AUTHOR   = escape(os.environ.get("SITE_AUTHOR", "Photographer"))
INSTAGRAM_URL = escape(os.environ.get("INSTAGRAM_URL", ""), quote=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Derived image sizes (long side for grid/preview, width for covers)
GRID_SIZE    = 1000    # album grid
PREVIEW_SIZE = 2000    # lightbox
COVER_SIZES  = (800, 1600, 2400)   # album cards + homepage hero

VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# --- Helpers -----------------------------------------------------------------

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def is_image(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(("._", "."))


def slugify(name: str) -> str:
    name = name.lower().replace(" ", "-").replace("'", "").replace("&", "and")
    return re.sub(r"[^a-z0-9\-]", "", name)


def nice_date(key) -> str:
    """(2026, 10, 14) -> '14 Oct 2026'"""
    if not key:
        return ""
    y, m, d = key
    return f"{d} {MONTHS[m - 1]} {y}"


@contextmanager
def local_copy(src: Path):
    """Open photos from a local temp copy: reading straight from the rclone
    mount occasionally returns truncated data."""
    with tempfile.NamedTemporaryFile(suffix=src.suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copyfile(src, tmp_path)
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


def is_fresh(src: Path, dst: Path) -> bool:
    """Derived file exists and is newer than its source (re-exported albums
    get regenerated instead of keeping a stale version)."""
    try:
        return dst.stat().st_mtime >= src.stat().st_mtime
    except FileNotFoundError:
        return False


def render(src: Path, dst: Path, max_w: int, max_h: int, quality: int):
    """Write a resized, EXIF-rotated JPEG. Atomic, so a crash never leaves a
    half-written image that would count as 'fresh'."""
    if is_fresh(src, dst):
        return False
    ensure_dir(dst.parent)
    with local_copy(src) as tmp, Image.open(tmp) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        part = dst.with_name(dst.name + ".part")
        img.save(part, "JPEG", quality=quality, optimize=True, progressive=True)
        part.replace(dst)
    return True

# --- Markdown (small subset) -------------------------------------------------

def inline_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)


def md_to_html(text: str) -> str:
    html, in_list = [], False
    for raw in text.splitlines():
        line = raw.strip()
        is_item = line.startswith("- ")
        if in_list and not is_item:
            html.append("</ul>")
            in_list = False
        if not line:
            continue
        if line in ("---", "***", "___"):
            html.append("<hr>")
        elif line.startswith("### "):
            html.append(f"<h3>{inline_md(line[4:])}</h3>")
        elif line.startswith("## "):
            html.append(f"<h2>{inline_md(line[3:])}</h2>")
        elif line.startswith("# "):
            html.append(f"<h1>{inline_md(line[2:])}</h1>")
        elif is_item:
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{inline_md(line[2:])}</li>")
        else:
            html.append(f"<p>{inline_md(line)}</p>")
    if in_list:
        html.append("</ul>")
    return "\n".join(html)


def read_md(path: Path) -> str:
    return md_to_html(path.read_text(encoding="utf-8")) if path.exists() else ""

# --- Photo metadata (cached) -------------------------------------------------

META_CACHE_FILE = OUTPUT_DIR / ".cache" / "meta.json"
_meta_cache = {}


def load_meta_cache():
    global _meta_cache
    try:
        _meta_cache = json.loads(META_CACHE_FILE.read_text())
    except (OSError, ValueError):
        _meta_cache = {}


def save_meta_cache():
    ensure_dir(META_CACHE_FILE.parent)
    META_CACHE_FILE.write_text(json.dumps(_meta_cache))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _clean(v) -> str:
    """EXIF strings are often padded with NUL bytes."""
    return str(v or "").replace("\x00", "").strip()


def _camera(make: str, model: str) -> str:
    make, model = _clean(make), _clean(model)
    short = make.split()[0].title() if make else ""
    if short and model.upper().startswith(short.upper()):
        model = model[len(short):].strip()
    # Nikon's internal names: "Z 6_2" -> "Z6 II"
    model = re.sub(r"\bZ (\d+)", r"Z\1", model)
    model = re.sub(r"_(\d)\b", lambda m: " " + {"2": "II", "3": "III"}.get(m.group(1), m.group(1)), model)
    if short and model:
        return f"{short} {model}"
    return model or short


def display_name(folder_name: str) -> str:
    """'historischfestival-almelo' -> 'Historischfestival almelo'."""
    name = re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", folder_name)).strip()
    return name[:1].upper() + name[1:]


def read_meta(photo: Path) -> dict:
    """Dimensions (after EXIF rotation) and a short EXIF summary, cached by
    path + mtime + size so rebuilds don't re-read every photo."""
    st = photo.stat()
    key = str(photo)
    sig = [st.st_mtime, st.st_size]
    hit = _meta_cache.get(key)
    if hit and hit.get("sig") == sig:
        return hit

    meta = {"sig": sig, "w": 3, "h": 2, "date": None, "camera": "",
            "lens": "", "focal": "", "fnum": "", "shutter": "", "iso": ""}
    try:
        with local_copy(photo) as tmp, Image.open(tmp) as img:
            w, h = img.size
            exif = img.getexif()
            if exif.get(274) in (5, 6, 7, 8):        # 90/270 graden gedraaid
                w, h = h, w
            meta["w"], meta["h"] = w, h
            sub = exif.get_ifd(0x8769)                # Exif sub-IFD
            raw_date = _clean(sub.get(36867) or exif.get(306))
            if raw_date:
                y, m, d = (int(x) for x in str(raw_date).split(" ")[0].split(":")[:3])
                meta["date"] = [y, m, d]
            meta["camera"] = _camera(exif.get(271), exif.get(272))
            meta["lens"] = _clean(sub.get(42036))
            focal = _num(sub.get(37386))
            if focal:
                meta["focal"] = f"{round(focal)}mm"
            fnum = _num(sub.get(33437))
            if fnum:
                meta["fnum"] = f"f/{fnum:g}"
            expo = _num(sub.get(33434))
            if expo:
                meta["shutter"] = f"1/{round(1 / expo)}s" if expo < 1 else f"{expo:g}s"
            iso = sub.get(34855)
            if isinstance(iso, (tuple, list)):
                iso = iso[0] if iso else None
            if iso:
                meta["iso"] = f"ISO {iso}"
    except Exception as exc:                          # kapotte foto: bouw gaat door
        print(f"[WARN]    EXIF/size failed for {photo.name}: {exc}")
    _meta_cache[key] = meta
    return meta


def exif_line(meta: dict):
    """List of (font-awesome icon, text) pairs for the lightbox."""
    items = []
    if meta.get("camera"):
        items.append(("fa-camera", meta["camera"]))
    if meta.get("lens"):
        items.append(("fa-circle-dot", meta["lens"]))
    settings = " · ".join(x for x in (meta.get("focal"), meta.get("fnum"),
                                       meta.get("shutter"), meta.get("iso")) if x)
    if settings:
        items.append(("fa-sliders", settings))
    return items

# --- Albums ------------------------------------------------------------------

def parse_notes(notes_path: Path):
    """Read notes.md; strip and return the date:/camera:/thumb_position: lines."""
    date_override = camera_override = thumb_pos_override = title = None
    if not notes_path.exists():
        return date_override, camera_override, thumb_pos_override, title, ""
    kept = []
    for line in notes_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("date:"):
            try:
                d, m, y = (int(x) for x in s.split(":", 1)[1].strip().split("-"))
                date_override = (y, m, d)
            except ValueError:
                pass
        elif low.startswith("camera:"):
            camera_override = s.split(":", 1)[1].strip()
        elif low.startswith("title:"):
            title = s.split(":", 1)[1].strip() or None
        elif low.startswith("thumb_position:"):
            val = s.split(":", 1)[1].strip().lower()
            if val in ("top", "center", "bottom", "left", "right"):
                thumb_pos_override = val
        else:
            kept.append(line)
    return date_override, camera_override, thumb_pos_override, title, md_to_html("\n".join(kept))


def scan_albums():
    albums = []
    if not PHOTOS_DIR.exists():
        print(f"[WARN] {PHOTOS_DIR} does not exist")
        return albums

    for album_dir in sorted(PHOTOS_DIR.iterdir()):
        if not album_dir.is_dir() or album_dir.name.startswith("."):
            continue
        photos = sorted((p for p in album_dir.iterdir() if is_image(p)),
                        key=lambda p: p.name.lower())
        if not photos:
            print(f"[SKIP] {album_dir.name}: no images found")
            continue

        date_override, camera_override, thumb_pos, title, notes_html = parse_notes(album_dir / "notes.md")

        cover = next((p for p in photos if p.stem.lower().startswith("cover")),
                     next((p for p in photos if not p.name.startswith("_")), photos[0]))
        gallery = [p for p in photos if not p.stem.lower().startswith("cover")] or photos
        metas = [read_meta(p) for p in gallery]

        # Date: notes.md > EXIF of the first photos > folder date. Never None,
        # so sorting the albums can't crash.
        date = date_override
        if not date:
            date = next((tuple(m["date"]) for m in metas[:5] if m["date"]), None)
        if not date:
            mt = datetime.fromtimestamp(album_dir.stat().st_mtime)
            date = (mt.year, mt.month, mt.day)

        camera = camera_override or next((m["camera"] for m in metas if m["camera"]), "")

        albums.append({
            "name":      escape(title or display_name(album_dir.name)),
            "slug":      slugify(album_dir.name),
            "dir":       album_dir,
            "photos":    gallery,
            "metas":     metas,
            "cover":     cover,
            "thumb_pos": thumb_pos or "center",
            "notes":     notes_html,
            "date":      date,
            "date_str":  nice_date(date),
            "camera":    camera,
        })
        print(f"[OK]   {album_dir.name}: {len(gallery)} photo(s), "
              f"date: {nice_date(date)}, camera: {camera or 'none'}")

    albums.sort(key=lambda a: a["date"], reverse=True)
    return albums

# --- Images ------------------------------------------------------------------

DERIVED_FORMAT = "2"   # ophogen = alle verkleinde foto's eenmalig opnieuw maken


def reset_derived_if_outdated():
    """Builds van voor 2.0 maakten previews zonder EXIF-rotatie en op een
    ander formaat. Die zouden als 'vers' blijven staan, dus bij een nieuw
    formaat de afgeleide mappen eenmalig weggooien (originelen blijven)."""
    marker = OUTPUT_DIR / ".cache" / "format"
    try:
        if marker.read_text().strip() == DERIVED_FORMAT:
            return
    except OSError:
        pass
    for sub in ("previews", "grid", "thumbs", "covers"):
        shutil.rmtree(OUTPUT_DIR / sub, ignore_errors=True)
        ensure_dir(OUTPUT_DIR / sub)
    ensure_dir(marker.parent)
    marker.write_text(DERIVED_FORMAT)
    print(f"[RESET]   derived images cleared for format {DERIVED_FORMAT}")


def build_images(albums):
    for a in albums:
        slug = a["slug"]
        made = 0
        for size in COVER_SIZES:
            made += render(a["cover"], OUTPUT_DIR / "covers" / slug / f"cover-{size}.jpg",
                           size, size, 82)
        # Old URL kept for anything that still links to it
        made += render(a["cover"], OUTPUT_DIR / "thumbs" / slug / "cover.jpg", 800, 800, 80)

        orig_dir = OUTPUT_DIR / "photos" / slug
        ensure_dir(orig_dir)
        for p in a["photos"]:
            made += render(p, OUTPUT_DIR / "grid" / slug / p.name, GRID_SIZE, GRID_SIZE, 80)
            made += render(p, OUTPUT_DIR / "previews" / slug / p.name, PREVIEW_SIZE, PREVIEW_SIZE, 85)
            dst = orig_dir / p.name
            if not is_fresh(p, dst):
                shutil.copyfile(p, dst)               # original; copy2 fails on rclone (xattrs)
                made += 1
        print(f"[IMG]     {a['name']}: {len(a['photos'])} photos, {made} file(s) (re)generated")


def prune_output(albums):
    """Remove pages and images of albums that no longer exist."""
    slugs = {a["slug"] for a in albums}
    for page in (OUTPUT_DIR / "albums").glob("*.html"):
        if page.stem not in slugs:
            page.unlink()
            print(f"[PRUNE]   albums/{page.name}")
    for sub in ("photos", "previews", "grid", "thumbs", "covers"):
        base = OUTPUT_DIR / sub
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if d.is_dir() and d.name not in slugs:
                shutil.rmtree(d)
                print(f"[PRUNE]   {sub}/{d.name}")


def copy_static():
    dst = OUTPUT_DIR / "assets"
    if STATIC_DIR.is_dir():
        shutil.copytree(STATIC_DIR, dst, dirs_exist_ok=True, copy_function=shutil.copyfile)
    me = CONTEXT_DIR / "me.jpg"
    if me.exists():
        render(me, OUTPUT_DIR / "me.jpg", 1200, 1500, 85)

# --- HTML --------------------------------------------------------------------

def cover_srcset(slug: str) -> str:
    return ", ".join(f"/covers/{slug}/cover-{s}.jpg {s}w" for s in COVER_SIZES)


def nav_html(active: str) -> str:
    def link(key, href, label):
        cls = "nav-link is-active" if key == active else "nav-link"
        cur = ' aria-current="page"' if key == active else ""
        return f'<a class="{cls}" href="{href}"{cur}>{label}</a>'
    insta = ""
    if INSTAGRAM_URL:
        insta = (f'<a class="icon-btn" href="{INSTAGRAM_URL}" target="_blank" rel="noopener" '
                 f'aria-label="Instagram"><i class="fa-brands fa-instagram"></i></a>')
    return f"""
<header class="nav">
  <div class="wrap nav-inner">
    <a class="wordmark" href="/">{SITE_TITLE}</a>
    <nav class="nav-links" aria-label="Main">
      {link("work", "/", "Work")}
      {link("about", "/gear.html", 'About<span class="hide-sm"> &amp; gear</span>')}
      {insta}
      <button class="icon-btn theme-toggle" type="button" aria-label="Toggle light / dark">
        <i class="fa-solid fa-moon"></i><i class="fa-solid fa-sun"></i>
      </button>
    </nav>
  </div>
</header>"""


def footer_html() -> str:
    year = datetime.now().year
    insta = (f'<a href="{INSTAGRAM_URL}" target="_blank" rel="noopener">'
             f'<i class="fa-brands fa-instagram"></i>Instagram</a>') if INSTAGRAM_URL else ""
    return f"""
<footer class="footer">
  <div class="wrap">
    <span>&copy; {year} {SITE_AUTHOR}. All photos are mine; please ask before using them.</span>
    <span class="footer-links">
      {insta}
      <a href="https://projecten.makkers.net" target="_blank" rel="noopener">projecten.makkers.net</a>
      <span>v{VERSION}</span>
    </span>
  </div>
</footer>"""


def base_html(title, active, body, *, description="", image="", body_class="", data_json=""):
    full_title = SITE_TITLE if title == SITE_TITLE else f"{title} — {SITE_TITLE}"
    desc = escape(description or f"Photography by {SITE_AUTHOR}.", quote=True)
    og_image = f'<meta property="og:image" content="{image}">' if image else ""
    data = (f'<script type="application/json" id="photo-data">{data_json}</script>'
            if data_json else "")
    return f"""<!DOCTYPE html>
<html lang="en" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{full_title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
{og_image}
<meta name="theme-color" content="#232634">
<script>
(function(){{var t;try{{t=localStorage.getItem('theme')}}catch(e){{}}
if(t!=='light'&&t!=='dark')t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
document.documentElement.dataset.theme=t;}})();
</script>
<link rel="preload" href="/assets/fonts/fraunces-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" integrity="sha512-SnH5WK+bZxgPHs44uWIX+LLJAJ9/2PkPKZ5QiAj6Ta86w+fsb2TkcmfRyVX3pBnMFcV7oQPJkl9QevSCWr3W6A==" crossorigin="anonymous" referrerpolicy="no-referrer">
<link rel="stylesheet" href="/assets/site.css?v={VERSION}">
</head>
<body class="{body_class}">
<a class="sr-only" href="#main">Skip to content</a>
{nav_html(active)}
<main id="main">
{body}
</main>
{footer_html()}
{data}
<script src="/assets/site.js?v={VERSION}" defer></script>
</body>
</html>"""


def album_meta_line(a) -> str:
    count = len(a["photos"])
    return f"{count} photo{'s' if count != 1 else ''} · {a['date_str']}"


def mosaic_layout(n):
    """Speelse mozaiek-indeling op een 12-koloms grid: groot/klein wisselt
    af, zodat de homepage geen rijtje gelijke blokjes wordt. Geeft per album
    (grid-column, grid-row, formaat) terug. Rijen zijn ~120 px hoog.

      blok A: groot links (7 kol, 4 rijen) + twee kleine rechts
      blok B: twee halve tegels naast elkaar (6 kol, 3 rijen)
      blok C: gespiegeld A, groot rechts
    Rest van 1 album: brede tegel; rest van 2: blok B.
    """
    out, row, i, blocks = [], 1, 0, "ABCB"
    b = 0
    while i < n:
        left = n - i
        kind = blocks[b % len(blocks)]
        if left == 1:
            out.append((f"1 / span 12", f"{row} / span 3", "lg"))
            i, row = i + 1, row + 3
        elif left == 2 or kind == "B":
            out += [(f"1 / span 6", f"{row} / span 3", "md"),
                    (f"7 / span 6", f"{row} / span 3", "md")]
            i, row = i + 2, row + 3
        elif kind == "A":
            out += [(f"1 / span 7", f"{row} / span 4", "lg"),
                    (f"8 / span 5", f"{row} / span 2", "sm"),
                    (f"8 / span 5", f"{row + 2} / span 2", "sm")]
            i, row = i + 3, row + 4
        else:                                   # C: groot rechts
            # kleine eerst, zodat de nummers links-naar-rechts oplopen
            out += [(f"1 / span 5", f"{row} / span 2", "sm"),
                    (f"1 / span 5", f"{row + 2} / span 2", "sm"),
                    (f"6 / span 7", f"{row} / span 4", "lg")]
            i, row = i + 3, row + 4
        b += 1
    return out[:n]


def build_index(albums):
    if not albums:
        body = '<div class="wrap album-head"><h1 class="album-title">No albums yet</h1></div>'
        (OUTPUT_DIR / "index.html").write_text(base_html(SITE_TITLE, "work", body))
        return

    hero = albums[0]
    hero_pos = f' style="object-position:{hero["thumb_pos"]}"' if hero["thumb_pos"] != "center" else ""
    intro = read_md(CONTEXT_DIR / "intro.md") or f"<p>Photography by {SITE_AUTHOR}.</p>"
    intro = re.sub(r"^<p>|</p>$", "", intro.strip())

    cards = []
    for i, (a, (col, row, size)) in enumerate(zip(albums, mosaic_layout(len(albums))), start=1):
        pos = f";object-position:{a['thumb_pos']}" if a["thumb_pos"] != "center" else ""
        sizes = {"lg": "(min-width: 760px) 60vw, 100vw",
                 "md": "(min-width: 760px) 50vw, 100vw",
                 "sm": "(min-width: 760px) 42vw, 100vw"}[size]
        cards.append(f"""
  <a class="tile tile-{size}" href="/albums/{a['slug']}.html" style="--col:{col};--row:{row}">
    <img class="fade" src="/covers/{a['slug']}/cover-800.jpg" srcset="{cover_srcset(a['slug'])}"
         sizes="{sizes}" alt="" loading="{'eager' if i <= 3 else 'lazy'}" decoding="async" style="{pos}">
    <span class="tile-info">
      <span class="tile-kicker">{i:02d} · {a['date_str']}</span>
      <span class="tile-title">{a['name']}</span>
      <span class="tile-meta">{len(a['photos'])} photos <i class="fa-solid fa-arrow-right"></i></span>
    </span>
  </a>""")

    n = len(albums)
    body = f"""
<section class="hero">
  <img class="fade" src="/covers/{hero['slug']}/cover-1600.jpg" srcset="{cover_srcset(hero['slug'])}"
       sizes="100vw" alt="{hero['name']}" fetchpriority="high"{hero_pos}>
  <div class="hero-content wrap">
    <p class="kicker">Latest album · {hero['date_str']}</p>
    <h1 class="hero-title">{hero['name']}</h1>
    <a class="hero-link" href="/albums/{hero['slug']}.html">View album <i class="fa-solid fa-arrow-right"></i></a>
  </div>
</section>

<div class="wrap">
  <section class="intro">
    <p class="kicker">{SITE_TITLE}</p>
    <p class="intro-text">{intro}</p>
  </section>

  <section aria-labelledby="albums-title">
    <div class="section-head">
      <h2 class="section-title" id="albums-title">Albums</h2>
      <span class="kicker">{n} album{'s' if n != 1 else ''}</span>
    </div>
    <div class="mosaic">{''.join(cards)}
    </div>
  </section>
</div>"""
    (OUTPUT_DIR / "index.html").write_text(base_html(
        SITE_TITLE, "work", body, body_class="has-hero",
        description=f"Photography by {SITE_AUTHOR}: {n} albums.",
        image=f"/covers/{hero['slug']}/cover-1600.jpg"))
    print("[BUILD] index.html")


def album_layout(metas):
    """Speels ritme voor de albumpagina in plaats van gelijke rijen.
    Blokken: een grote foto over de volle breedte, rijen van drie en
    paren. Alles in de eigen verhouding: er wordt niets bijgesneden.
    Een 'feature' vraagt een liggende foto; anders wordt het een rij.
    Geeft [(soort, [indexen])] terug in leesvolgorde."""
    n = len(metas)
    ratio = [m["w"] / m["h"] if m["h"] else 1.5 for m in metas]
    cycle = ["feature", "row", "pair", "row", "pair-flip"]
    blocks, i, c = [], 0, 0
    while i < n:
        kind = cycle[c % len(cycle)]
        left = n - i
        if kind == "feature" and ratio[i] < 1.25:
            kind = "row"
        if kind.startswith("pair") and left < 2:
            kind = "feature" if ratio[i] >= 1.25 else "row"
        if kind == "feature":
            blocks.append((kind, [i]))
            i += 1
        elif kind.startswith("pair"):
            blocks.append((kind, [i, i + 1]))
            i += 2
        else:
            take = 3 if left != 4 else 2       # 4 over: liever 2+2 dan 3+1
            take = min(take, left)
            blocks.append(("row", list(range(i, i + take))))
            i += take
        c += 1
    return blocks


def build_album(a, prev_a, next_a):
    slug = a["slug"]
    data, tiles = [], []
    for i, (p, m) in enumerate(zip(a["photos"], a["metas"])):
        name = quote(p.name)
        ratio = round(m["w"] / m["h"], 4) if m["h"] else 1.5
        alt = f"{a['name']}, photo {i + 1}"
        tiles.append((name, ratio, alt, i))
        data.append({"full": f"/previews/{slug}/{name}", "orig": f"/photos/{slug}/{name}",
                     "alt": alt, "exif": exif_line(m)})

    def tile(idx, sizes):
        name, ratio, alt, i = tiles[idx]
        return (f'<a class="photo" href="/previews/{slug}/{name}" style="--r:{ratio}" data-n="{i + 1:02d}">'
                f'<img class="fade" src="/grid/{slug}/{name}" '
                f'srcset="/grid/{slug}/{name} {GRID_SIZE}w, /previews/{slug}/{name} {PREVIEW_SIZE}w" '
                f'sizes="{sizes}" alt="{alt}" loading="{"eager" if i < 3 else "lazy"}" '
                f'decoding="async"></a>')

    blocks_html = []
    for kind, idxs in album_layout(a["metas"]):
        if kind == "feature":
            inner = tile(idxs[0], "(min-width: 900px) 90vw, 100vw")
            blocks_html.append(f'<div class="blk blk-feature reveal">{inner}</div>')
        elif kind.startswith("pair"):
            flip = " is-flip" if kind == "pair-flip" else ""
            # twee foto's in hun eigen verhouding, even hoog en strak tegen
            # elkaar: niets bijgesneden, geen witte vlakken
            inner = (tile(idxs[0], "(min-width: 760px) 50vw, 50vw")
                     + tile(idxs[1], "(min-width: 760px) 50vw, 50vw"))
            blocks_html.append(f'<div class="blk blk-pair{flip} reveal">{inner}</div>')
        else:
            inner = "".join(tile(j, "(min-width: 760px) 34vw, 50vw") for j in idxs)
            blocks_html.append(f'<div class="blk blk-row reveal">{inner}</div>')

    meta = [f'<span><i class="fa-regular fa-calendar"></i>{a["date_str"]}</span>',
            f'<span><i class="fa-regular fa-images"></i>{len(a["photos"])} photos</span>']
    if a["camera"]:
        meta.append(f'<span><i class="fa-solid fa-camera"></i>{escape(a["camera"])}</span>')
    notes = f'<div class="prose">{a["notes"]}</div>' if a["notes"] else ""

    def nav_link(other, cls, label):
        if not other:
            return "<span></span>"
        img = f'<img src="/covers/{other["slug"]}/cover-800.jpg" alt="" loading="lazy">'
        text = (f'<span><span class="kicker">{label}</span>'
                f'<span class="album-nav-title">{other["name"]}</span></span>')
        inner = f"{img}{text}" if cls == "is-prev" else f"{text}{img}"
        return f'<a class="{cls}" href="/albums/{other["slug"]}.html">{inner}</a>'

    body = f"""
<div class="wrap">
  <header class="album-head">
    <a class="back" href="/"><i class="fa-solid fa-arrow-left"></i> All albums</a>
    <div class="album-head-grid">
      <h1 class="album-title">{a['name']}</h1>
      <div class="album-head-side">
        <div class="album-meta">{''.join(meta)}</div>
        {notes}
      </div>
    </div>
  </header>
  <div class="photos">{''.join(blocks_html)}</div>

  <nav class="album-nav" aria-label="More albums">
    {nav_link(prev_a, "is-prev", "Newer")}
    {nav_link(next_a, "is-next", "Older")}
  </nav>
</div>

<div class="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-label="Photo viewer" aria-hidden="true">
  <div class="lb-top">
    <span class="lb-counter"></span>
    <div class="lb-actions">
      <a class="icon-btn lb-original" href="#" target="_blank" rel="noopener" aria-label="Open original"><i class="fa-solid fa-up-right-from-square"></i></a>
      <button class="icon-btn lb-close" type="button" aria-label="Close"><i class="fa-solid fa-xmark"></i></button>
    </div>
  </div>
  <div class="lb-stage">
    <img class="lb-img" src="" alt="">
    <button class="lb-nav lb-prev" type="button" aria-label="Previous photo"><i class="fa-solid fa-chevron-left"></i></button>
    <button class="lb-nav lb-next" type="button" aria-label="Next photo"><i class="fa-solid fa-chevron-right"></i></button>
  </div>
  <div class="lb-bottom">
    <div class="lb-exif"></div>
    <span class="lb-hint">&larr; &rarr; to browse · Esc to close</span>
  </div>
</div>"""
    # '</' in JSON could close the script tag
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = OUTPUT_DIR / "albums" / f"{slug}.html"
    out.write_text(base_html(
        a["name"], "work", body, data_json=data_json,
        description=f"{a['name']}: {album_meta_line(a)}. Photography by {SITE_AUTHOR}.",
        image=f"/covers/{slug}/cover-1600.jpg"))
    print(f"[BUILD] albums/{slug}.html")


def gear_html(path: Path) -> str:
    """gear.md: '## Category' headings with '- **Name** — description' items."""
    if not path.exists():
        return ""
    groups, intro, cur = [], [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("## "):
            cur = {"title": s[3:], "rows": []}
            groups.append(cur)
        elif s.startswith("- ") and cur is not None:
            m = re.match(r"\*\*(.+?)\*\*\s*[-—–]\s*(.*)", s[2:])
            name, desc = (m.group(1), m.group(2)) if m else (s[2:].replace("**", ""), "")
            cur["rows"].append(f'<div class="gear-row"><dt>{name}</dt><dd>{inline_md(desc)}</dd></div>')
        elif cur is None:
            intro.append(f"<p>{inline_md(s)}</p>")
    out = [f'<div class="prose">{"".join(intro)}</div>'] if intro else []
    for g in groups:
        out.append(f'<section class="gear-group"><h3 class="kicker">{g["title"]}</h3>'
                   f'<dl>{"".join(g["rows"])}</dl></section>')
    return "\n".join(out)


def build_gear():
    about = read_md(CONTEXT_DIR / "about.md") or "<p>Edit <code>context/about.md</code>.</p>"
    gear = gear_html(CONTEXT_DIR / "gear.md")
    gear_block = (f'<div class="gear"><div class="section-head"><h2 class="section-title">Gear</h2></div>'
                  f'{gear}</div>') if gear else ""
    if (OUTPUT_DIR / "me.jpg").exists():
        side = (f'<div class="about-photo"><img class="fade" src="/me.jpg" alt="{SITE_AUTHOR}"></div>')
        title = '<h1 class="album-title">About &amp; gear</h1>'
    else:
        # Geen foto: de titel krijgt de linkerkolom (zet context/me.jpg neer voor een portret)
        side = ('<div class="about-side"><p class="kicker">Hello</p>'
                '<h1 class="album-title">About &amp; gear</h1></div>')
        title = ""
    body = f"""
<div class="wrap">
  <div class="about">
    {side}
    <div>
      {title}
      <div class="prose prose-lead">{about}</div>
      {gear_block}
    </div>
  </div>
</div>"""
    (OUTPUT_DIR / "gear.html").write_text(base_html("About & gear", "about", body))
    print("[BUILD] gear.html")

# --- Main --------------------------------------------------------------------

def main():
    print(f"\n{'=' * 50}\n  Purrfolio builder v{VERSION}")
    print(f"  Photos  : {PHOTOS_DIR.resolve()}")
    print(f"  Output  : {OUTPUT_DIR.resolve()}")
    print(f"  Context : {CONTEXT_DIR.resolve()}\n{'=' * 50}\n")

    for sub in ("", "albums", "photos", "previews", "grid", "thumbs", "covers"):
        ensure_dir(OUTPUT_DIR / sub)
    reset_derived_if_outdated()
    load_meta_cache()

    albums = scan_albums()
    print(f"\n{len(albums)} album(s) found\n")
    save_meta_cache()

    build_images(albums)
    prune_output(albums)
    copy_static()

    print()
    build_index(albums)
    for i, a in enumerate(albums):
        prev_a = albums[i - 1] if i > 0 else None
        next_a = albums[i + 1] if i + 1 < len(albums) else None
        build_album(a, prev_a, next_a)
    build_gear()

    print(f"\nDone. Site written to {OUTPUT_DIR.resolve()}")
    print(f"  {len(albums)} albums, {sum(len(a['photos']) for a in albums)} photos total\n")


if __name__ == "__main__":
    main()
