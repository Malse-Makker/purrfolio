#!/usr/bin/env python3
"""
Purrfolio - static site generator
Scans the photos directory and outputs a plain HTML site into the output directory.
"""

import os
import re
import shutil
from html import escape
from urllib.parse import quote
from pathlib import Path
from PIL import Image

# --- Configuration -----------------------------------------------------------

PHOTOS_DIR    = Path(os.environ.get("PHOTOS_DIR", "./photos"))
OUTPUT_DIR    = Path(os.environ.get("OUTPUT_DIR", "./output"))
CONTEXT_DIR   = Path(os.environ.get("CONTEXT_DIR", "./context"))
SITE_TITLE    = escape(os.environ.get("SITE_TITLE", "My Portfolio"))
SITE_AUTHOR   = escape(os.environ.get("SITE_AUTHOR", "Photographer"))
INSTAGRAM_URL = escape(os.environ.get("INSTAGRAM_URL", ""), quote=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
THUMB_SIZE   = (600, 400)
PREVIEW_SIZE = 1800   # max width for masonry preview images

# --- Helpers -----------------------------------------------------------------

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def is_image(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("._")

def make_thumbnail(src: Path, dst: Path):
    """Resize to max 800px wide, no cropping. Browser handles positioning via object-fit."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=src.suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copy(src, tmp_path)
        with Image.open(tmp_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            max_w = 800
            if w > max_w:
                ratio = max_w / w
                img = img.resize((max_w, int(h * ratio)), Image.LANCZOS)
            img.save(dst, "JPEG", quality=80, optimize=True)
    finally:
        tmp_path.unlink(missing_ok=True)

def make_preview(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=src.suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copy(src, tmp_path)
        with Image.open(tmp_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if w > PREVIEW_SIZE:
                ratio = PREVIEW_SIZE / w
                img = img.resize((PREVIEW_SIZE, int(h * ratio)), Image.LANCZOS)
            img.save(dst, "JPEG", quality=78, optimize=True)
    finally:
        tmp_path.unlink(missing_ok=True)

def slugify(name: str) -> str:
    name = name.lower().replace(" ", "-").replace("'", "").replace("&", "and")
    return re.sub(r"[^a-z0-9\-]", "", name)

def md_to_html(text: str) -> str:
    html = ""
    in_list = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if in_list:
                html += "</ul>\n"
                in_list = False
            html += "<br>\n"
            continue
        if line in ("---", "***", "___"):
            if in_list: html += "</ul>\n"; in_list = False
            html += "<hr style=\"border:none;border-top:0.5px solid var(--border);margin:16px 0\">\n"
            continue
        if line.startswith("### "):
            if in_list: html += "</ul>\n"; in_list = False
            html += f"<h3>{line[4:]}</h3>\n"
        elif line.startswith("## "):
            if in_list: html += "</ul>\n"; in_list = False
            html += f"<h2>{line[3:]}</h2>\n"
        elif line.startswith("# "):
            if in_list: html += "</ul>\n"; in_list = False
            html += f"<h1>{line[2:]}</h1>\n"
        elif line.startswith("- "):
            if not in_list: html += "<ul>\n"; in_list = True
            item = line[2:]
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            item = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         item)
            item = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', item)
            html += f"<li>{item}</li>\n"
        else:
            if in_list: html += "</ul>\n"; in_list = False
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         line)
            line = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" style="color:var(--accent);border-bottom:1px solid var(--border)">\1</a>', line)
            html += f"<p>{line}</p>\n"
    if in_list:
        html += "</ul>\n"
    return html

def read_md(path: Path) -> str:
    if path.exists():
        return md_to_html(path.read_text(encoding="utf-8"))
    return ""

def copy_asset(src: Path, dst: Path):
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
        return True
    return False

def exif_date(photo: Path):
    """Extract DateTimeOriginal from EXIF. Returns sortable tuple and display string, or None."""
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=photo.suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            shutil.copy(photo, tmp_path)
            with Image.open(tmp_path) as img:
                exif = img._getexif()
                if exif:
                    # 36867 = DateTimeOriginal, 306 = DateTime
                    for tag in (36867, 306):
                        val = exif.get(tag)
                        if val:
                            # Format: YYYY:MM:DD HH:MM:SS
                            date_part = val.split(" ")[0]
                            y, m, d = date_part.split(":")
                            y, m, d = int(y), int(m), int(d)
                            return (y, m, d), f"{d:02d}-{m:02d}-{y}"
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        pass
    return None, ""

def exif_camera(photo: Path):
    """Extract camera make+model from EXIF. Returns string or empty."""
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=photo.suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            shutil.copy(photo, tmp_path)
            with Image.open(tmp_path) as img:
                exif = img._getexif()
                if exif:
                    make  = (exif.get(271) or "").strip()
                    model = (exif.get(272) or "").strip()
                    # Normalize make to first word, title-cased (e.g. "NIKON CORPORATION" -> "Nikon")
                    short_make = make.split()[0].title() if make else ""
                    # Strip make prefix from model if present (e.g. "NIKON D700" -> "D700")
                    model_clean = model
                    if short_make and model.upper().startswith(short_make.upper()):
                        model_clean = model[len(short_make):].strip()
                    elif make and model.upper().startswith(make.split()[0].upper()):
                        model_clean = model[len(make.split()[0]):].strip()
                    if short_make and model_clean:
                        return f"{short_make} {model_clean}"
                    return model_clean or short_make or model or make
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        pass
    return ""

def parse_notes(notes_path: Path):
    """Parse notes.md, extract date:, camera:, thumb_position: meta lines, return parsed values and html."""
    date_override      = None
    camera_override    = None
    thumb_pos_override = None
    if notes_path.exists():
        lines = notes_path.read_text(encoding="utf-8").splitlines()
        kept  = []
        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith("date:"):
                raw = stripped.split(":", 1)[1].strip()
                try:
                    parts = raw.split("-")
                    d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    date_override = (y, m, d), f"{d:02d}-{m:02d}-{y}"
                except Exception:
                    pass
            elif stripped.lower().startswith("camera:"):
                camera_override = stripped.split(":", 1)[1].strip()
            elif stripped.lower().startswith("thumb_position:"):
                val = stripped.split(":", 1)[1].strip().lower()
                if val in ("top", "center", "bottom", "left", "right"):
                    thumb_pos_override = val
            else:
                kept.append(line)
        notes_html = md_to_html("\n".join(kept))
    else:
        notes_html = ""
    return date_override, camera_override, thumb_pos_override, notes_html

# --- Scan albums -------------------------------------------------------------

def scan_albums():
    albums = []
    if not PHOTOS_DIR.exists():
        print(f"[WARN] {PHOTOS_DIR} does not exist")
        return albums

    for album_dir in sorted(PHOTOS_DIR.iterdir()):
        if not album_dir.is_dir():
            continue
        photos = sorted([p for p in album_dir.iterdir() if is_image(p)])
        if not photos:
            print(f"[SKIP] {album_dir.name}: no images found")
            continue
        notes_path = album_dir / "notes.md"
        date_override, camera_override, thumb_pos_override, notes_html = parse_notes(notes_path)

        # Sort photos by name so cover.jpg / 00_cover.jpg always comes first
        photos = sorted(photos, key=lambda p: p.name.lower())

        # Pick cover: prefer file starting with "cover", else first non-underscore/dot file
        cover = next((p for p in photos if p.stem.lower().startswith("cover")),
                     next((p for p in photos if not p.name.startswith(("_", "."))), photos[0]))

        # Exclude cover file from the album gallery (it's only used as thumbnail)
        gallery_photos = [p for p in photos if not p.stem.lower().startswith("cover")]
        if not gallery_photos:
            gallery_photos = photos  # fallback if all photos are named cover*

        # Date: notes.md overrides EXIF
        if date_override:
            sort_key, date_str = date_override
        else:
            sort_key, date_str = exif_date(photos[0])

        # Camera: notes.md overrides EXIF
        if camera_override:
            camera_str = camera_override
        else:
            camera_str = exif_camera(photos[0])

        # Thumb position: notes.md or default center
        thumb_pos = thumb_pos_override or "center"

        albums.append({
            "name":          escape(album_dir.name),
            "slug":          slugify(album_dir.name),
            "dir":           album_dir,
            "photos":        gallery_photos,
            "all_photos":    photos,
            "thumbnail":     cover,
            "thumb_pos":     thumb_pos,
            "notes":         notes_html,
            "date_str":      date_str,
            "sort_key":      sort_key,
            "camera_str":    camera_str,
        })
        has_notes = "yes" if notes_path.exists() else "no"
        cover_excluded = len(photos) - len(gallery_photos)
        print(f"[OK]   {album_dir.name}: {len(gallery_photos)} photo(s) "
              f"({cover_excluded} cover excluded), date: {date_str or 'none'}, camera: {camera_str or 'none'}, thumb: {thumb_pos}")

    # Sort newest first
    albums.sort(key=lambda a: a["sort_key"], reverse=True)
    return albums

# --- HTML templates ----------------------------------------------------------

THEME_CSS = """
html,body{--bg:#eff1f5;--bg2:#e6e9ef;--text:#4c4f69;--text2:#6c6f85;--accent:#8839ef;--border:rgba(76,79,105,.15);--card:#eff1f5}
html.theme-frappe,html.theme-frappe body{--bg:#303446;--bg2:#292c3c;--text:#c6d0f5;--text2:#a5adce;--accent:#ca9ee6;--border:rgba(198,208,245,.15);--card:#363a4f}
"""

THEME_INLINE = """
(function(){
  var t=localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'frappe':'latte');
  document.documentElement.className=t==='latte'?'':'theme-'+t;
})();
"""

BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html{background:var(--bg)}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);transition:background .3s,color .3s}
a{color:inherit;text-decoration:none}
nav{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 28px;display:flex;align-items:center;justify-content:space-between;height:58px;position:sticky;top:0;z-index:99}
.site-title{font-size:15px;font-weight:600;letter-spacing:.06em;text-transform:uppercase}
.nav-links{display:flex;gap:28px;align-items:center}
.nav-link{font-size:13px;color:var(--text2);border-bottom:1.5px solid transparent;padding:4px 0;transition:color .2s,border-color .2s;letter-spacing:.02em}
.nav-link:hover,.nav-link.active{color:var(--accent);border-color:var(--accent)}
.theme-switcher{display:flex;gap:4px}
.theme-btn{width:32px;height:32px;border-radius:50%;border:1px solid var(--border);background:transparent;color:var(--text2);cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;transition:border-color .2s,color .2s,transform .15s}
.theme-btn:hover{transform:scale(1.1);color:var(--text)}
.theme-btn.active{border-color:var(--accent);color:var(--accent)}
main{padding:40px 28px;max-width:1200px;margin:0 auto}
h1{font-size:24px;font-weight:400;letter-spacing:.04em;margin-bottom:6px}
.subtitle{font-size:12px;color:var(--text2);margin-bottom:36px;letter-spacing:.05em;text-transform:uppercase}
.gallery-grid{display:grid;gap:3px}
.gallery-item{position:relative;overflow:hidden;cursor:pointer;display:block}
.gallery-item img{width:100%;height:100%;object-fit:cover;object-position:center;display:block;transition:transform .4s ease}
.gallery-item:hover img{transform:scale(1.03)}
.gallery-overlay{position:absolute;bottom:0;left:0;right:0;padding:20px 18px 16px;background:linear-gradient(transparent,rgba(0,0,0,.65))}
.gallery-overlay .album-name{font-size:15px;font-weight:500;color:#fff;letter-spacing:.02em}
.gallery-overlay .album-meta{font-size:11px;color:rgba(255,255,255,.6);margin-top:3px;letter-spacing:.04em}
.back{display:inline-flex;align-items:center;gap:8px;font-size:12px;color:var(--text2);margin-bottom:24px;transition:color .2s;letter-spacing:.04em;text-transform:uppercase}
.back:hover{color:var(--text)}
.back i{font-size:11px}
.album-notes{max-width:640px;margin-bottom:32px;padding:20px 24px;background:var(--card);border:1px solid var(--border);border-radius:8px}
.album-notes h2,.album-notes h3{font-size:14px;font-weight:500;margin-bottom:8px;margin-top:16px;color:var(--text)}
.album-notes h2:first-child,.album-notes h3:first-child{margin-top:0}
.album-notes p{font-size:13px;line-height:1.75;color:var(--text2);margin-bottom:6px}
.album-notes strong{color:var(--text)}
.photo-masonry{columns:3 260px;gap:10px;margin-top:24px}
.photo-item{break-inside:avoid;margin-bottom:10px;border-radius:6px;overflow:hidden;cursor:pointer;transition:opacity .2s}
.photo-item:hover{opacity:.85}
.photo-item img{width:100%;height:auto;display:block}
.lightbox{display:none;position:fixed;inset:0;background:rgba(0,0,0,.93);z-index:999;align-items:center;justify-content:center;flex-direction:column;gap:14px}
.lightbox.open{display:flex}
.lightbox img{max-width:92vw;max-height:85vh;object-fit:contain;border-radius:4px}
.lightbox-close{position:absolute;top:20px;right:24px;font-size:18px;color:rgba(255,255,255,.5);cursor:pointer;background:none;border:none;transition:color .2s;padding:6px}
.lightbox-close:hover{color:#fff}
.lightbox-nav{position:absolute;top:50%;transform:translateY(-50%);background:none;border:none;color:rgba(255,255,255,.4);font-size:20px;cursor:pointer;padding:12px;transition:color .2s}
.lightbox-nav:hover{color:#fff}
.lightbox-prev{left:16px}
.lightbox-next{right:16px}
.lightbox-caption{color:rgba(255,255,255,.4);font-size:12px;letter-spacing:.06em}
.about-layout{display:flex;gap:40px;align-items:flex-start;max-width:740px;margin-bottom:40px;padding-bottom:32px;border-bottom:1px solid var(--border)}
.about-photo{width:160px;flex-shrink:0;border-radius:8px;overflow:hidden}
.about-photo img{width:100%;height:auto;display:block}
.about-text h1,.about-text h2,.about-text h3{font-size:15px;font-weight:500;margin-bottom:8px;margin-top:20px;color:var(--text)}
.about-text h1:first-child,.about-text h2:first-child,.about-text h3:first-child{margin-top:0}
.about-text p{font-size:14px;line-height:1.75;color:var(--text2);margin-bottom:6px}
.about-text strong{color:var(--text)}
.gear-page{display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:start;max-width:900px;margin:0 auto}
.gear-page-title{grid-column:1/3;font-size:24px;font-weight:400;letter-spacing:.04em;margin-bottom:6px}
.gear-about .about-name{font-size:16px;font-weight:500;color:var(--text);margin-bottom:12px}
.gear-about .about-photo-wrap{width:100%;max-width:200px;border-radius:8px;overflow:hidden;margin-bottom:16px}
.gear-about .about-photo-wrap img{width:100%;height:auto;display:block}
.gear-about p{font-size:13px;line-height:1.75;color:var(--text2);margin-bottom:6px}
.gear-about strong{color:var(--text)}
.gear-about a{color:var(--accent)}
.gear-about br{display:block;margin-bottom:4px}
.gear-list .gcat{font-size:10px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--text2);padding:10px 0 5px;border-bottom:0.5px solid var(--border);margin-top:20px}
.gear-list .gcat:first-child{margin-top:0}
.gear-list .grow{display:flex;justify-content:space-between;align-items:baseline;padding:7px 0;border-bottom:0.5px solid var(--border)}
.gear-list .grow:last-child{border-bottom:none}
.gear-list .grn{font-size:13px;color:var(--text)}
.gear-list .grd{font-size:12px;color:var(--text2)}
@media(max-width:600px){.gear-page{grid-template-columns:1fr}}
footer{text-align:center;font-size:11px;color:var(--text2);padding:28px 0;border-top:1px solid var(--border);margin-top:48px;letter-spacing:.05em}
footer a{color:var(--text2);text-decoration:none;border-bottom:1px solid var(--border);transition:color .2s,border-color .2s;padding-bottom:1px}
footer a:hover{color:var(--text);border-color:var(--text)}
@media(max-width:520px){.about-layout{flex-direction:column}.about-photo{width:100%}}
"""

THEME_JS = """
const THEMES = ['latte','frappe'];
const btns = document.querySelectorAll('.theme-btn');
function applyTheme(t) {
  document.documentElement.className = t === 'latte' ? '' : 'theme-' + t;
  btns.forEach((b,i) => b.classList.toggle('active', THEMES[i] === t));
  localStorage.setItem('theme', t);
}
btns.forEach((b, i) => b.addEventListener('click', () => applyTheme(THEMES[i])));
const saved = localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'frappe' : 'latte');
applyTheme(saved);
"""

LIGHTBOX_JS = """
const lb    = document.getElementById('lightbox');
const lbImg = document.getElementById('lb-img');
const lbCap = document.getElementById('lb-cap');
const photos = Array.from(document.querySelectorAll('.photo-item'));
let cur = 0;
function openLb(idx) {
  cur = idx;
  lbImg.src = photos[idx].dataset.src;
  lbCap.textContent = photos[idx].dataset.caption;
  lb.classList.add('open');
}
function closeLb() { lb.classList.remove('open'); }
function prev() { openLb((cur - 1 + photos.length) % photos.length); }
function next() { openLb((cur + 1) % photos.length); }
photos.forEach((el, i) => el.addEventListener('click', () => openLb(i)));
document.getElementById('lb-close').addEventListener('click', closeLb);
document.getElementById('lb-prev').addEventListener('click', prev);
document.getElementById('lb-next').addEventListener('click', next);
lb.addEventListener('click', e => { if (e.target === lb) closeLb(); });
document.addEventListener('keydown', e => {
  if (!lb.classList.contains('open')) return;
  if (e.key === 'Escape')     closeLb();
  if (e.key === 'ArrowLeft')  prev();
  if (e.key === 'ArrowRight') next();
});
"""

VERSION = (Path(__file__).parent / "VERSION").read_text().strip()

def footer_html() -> str:
    parts = [f"&copy; {SITE_AUTHOR}"]
    if INSTAGRAM_URL:
        parts.append(f'<a href="{INSTAGRAM_URL}" target="_blank" rel="noopener"><i class="fa-brands fa-instagram"></i> Instagram</a>')
    parts.append(f'<a href="https://projecten.makkers.net" target="_blank" rel="noopener">projecten.makkers.net</a>')
    parts.append(f'<span>{VERSION}</span>')
    return "<footer>" + " &nbsp;&middot;&nbsp; ".join(parts) + "</footer>"

def nav_html(active: str) -> str:
    links = [("gallery", "index.html", "Gallery"), ("gear", "gear.html", "My gear &amp; me")]
    items = ""
    for key, href, label in links:
        cls = "nav-link active" if key == active else "nav-link"
        items += f'<a class="{cls}" href="/{href}">{label}</a>\n'
    return f"""
<nav>
  <span class="site-title">{SITE_TITLE}</span>
  <div class="nav-links">{items}</div>
  <div class="theme-switcher">
    <button class="theme-btn" title="Latte" aria-label="Catppuccin Latte"><i class="fa-solid fa-sun"></i></button>
    <button class="theme-btn" title="Frappe" aria-label="Catppuccin Frappe"><i class="fa-solid fa-moon"></i></button>
  </div>
</nav>"""

def base_html(title: str, active: str, body: str, extra_js: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — {SITE_TITLE}</title>
<script>{THEME_INLINE}</script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" integrity="sha512-SnH5WK+bZxgPHs44uWIX+LLJAJ9/2PkPKZ5QiAj6Ta86w+fsb2TkcmfRyVX3pBnMFcV7oQPJkl9QevSCWr3W6A==" crossorigin="anonymous" referrerpolicy="no-referrer">
<style>{THEME_CSS}{BASE_CSS}</style>
</head>
<body>
{nav_html(active)}
<main>{body}</main>
{footer_html()}
<script>{THEME_JS}{extra_js}</script>
</body>
</html>"""

# --- Page builders -----------------------------------------------------------

def gallery_layout(albums):
    """
    Returns list of (grid_column, grid_row) tuples for each album,
    plus (col_def, row_def) strings for the grid container.

    Layout rules:
      1 album  : full width
      2 albums : two equal columns
      3 albums : big left (spans 2 rows) + 2 small right
      4 albums : big left + 2 small right + 1 full-width bottom
      5+       : groups of 3 alternating:
                   odd  group: big LEFT  (col1, spans 2 rows) + small1 (col2 row1) + small2 (col2 row2)
                   even group: big RIGHT (col2, spans 2 rows) + small1 (col1 row1) + small2 (col1 row2)
                 leftover 1: full-width row
                 leftover 2: two equal columns row
    """
    n = len(albums)
    ROW_BIG   = "260px"
    ROW_SMALL = "150px"
    ROW_FULL  = "200px"

    if n == 1:
        return [("1/3", "1")], "grid-template-columns:2fr 1fr", f"grid-template-rows:{ROW_FULL}"

    if n == 2:
        placements = [("1", "1"), ("2", "1")]
        return placements, "grid-template-columns:1fr 1fr", f"grid-template-rows:{ROW_FULL}"

    if n == 3:
        placements = [("1", "1/3"), ("2", "1"), ("2", "2")]
        return placements, "grid-template-columns:2fr 1fr", f"grid-template-rows:{ROW_SMALL} {ROW_SMALL}"

    if n == 4:
        placements = [("1", "1/3"), ("2", "1"), ("2", "2"), ("1/3", "3")]
        return placements, "grid-template-columns:2fr 1fr", f"grid-template-rows:{ROW_SMALL} {ROW_SMALL} {ROW_FULL}"

    # 5+ albums: process in groups of 3 after first 3
    placements = []
    row_defs   = []
    current_row = 1

    i = 0
    group_idx = 0
    while i < n:
        remaining = n - i
        if remaining == 1:
            placements.append(("1/3", f"{current_row}"))
            row_defs.append(ROW_FULL)
            current_row += 1
            i += 1
        elif remaining == 2:
            placements.append(("1", f"{current_row}"))
            placements.append(("2", f"{current_row}"))
            row_defs.append(ROW_FULL)
            current_row += 1
            i += 2
        else:
            # group of 3
            r1, r2 = current_row, current_row + 1
            row_defs.append(ROW_SMALL)
            row_defs.append(ROW_SMALL)
            if group_idx % 2 == 0:
                # big LEFT
                placements.append(("1", f"{r1}/{r2+1}"))  # big
                placements.append(("2", f"{r1}"))          # small top
                placements.append(("2", f"{r2}"))          # small bottom
            else:
                # big RIGHT
                placements.append(("2", f"{r1}/{r2+1}"))  # big
                placements.append(("1", f"{r1}"))          # small top
                placements.append(("1", f"{r2}"))          # small bottom
            current_row += 2
            i += 3
            group_idx += 1

    col_def = "grid-template-columns:2fr 1fr"
    row_def = f"grid-template-rows:{' '.join(row_defs)}"
    return placements, col_def, row_def


def build_index(albums):
    n = len(albums)
    if n == 0:
        body = '<h1>Gallery</h1><p class="subtitle">No albums yet.</p>'
        (OUTPUT_DIR / "index.html").write_text(base_html("Gallery", "gallery", body))
        print("[BUILD] index.html")
        return

    placements, col_def, row_def = gallery_layout(albums)
    items = ""
    for i, a in enumerate(albums):
        thumb_path = f"thumbs/{a['slug']}/cover.jpg"
        count = len(a['photos'])
        meta = f"{count} photo{'s' if count != 1 else ''}"
        if a['date_str']:
            meta += f" &nbsp;·&nbsp; {a['date_str']}"
        col, row = placements[i]
        item_style = f"grid-column:{col};grid-row:{row}"
        img_style = f'style="object-position:{a["thumb_pos"]}"' if a["thumb_pos"] != "center" else ""
        loading = "eager" if i < 3 else "lazy"
        items += f"""
<a class="gallery-item" href="/albums/{a['slug']}.html" style="{item_style}">
  <img src="/{thumb_path}" alt="{a['name']}" loading="{loading}" {img_style}>
  <div class="gallery-overlay">
    <div class="album-name">{a['name']}</div>
    <div class="album-meta">{meta}</div>
  </div>
</a>"""

    grid_style = f"{col_def};{row_def}"
    body = f"""
<h1>Gallery</h1>
<p class="subtitle">{n} album{'s' if n != 1 else ''}</p>
<div class="gallery-grid" style="{grid_style}">{items}</div>"""

    (OUTPUT_DIR / "index.html").write_text(base_html("Gallery", "gallery", body))
    print("[BUILD] index.html")

def build_album(album):
    photos_html = ""
    for i, p in enumerate(album["photos"]):
        original_path = f"/photos/{album['slug']}/{quote(p.name)}"
        preview_path  = f"/previews/{album['slug']}/{quote(p.name)}"
        caption = escape(p.stem, quote=True)
        photos_html += f"""
<div class="photo-item" data-src="{original_path}" data-caption="{caption}">
  <img src="{preview_path}" alt="{caption}" loading="{'eager' if i < 6 else 'lazy'}">
</div>"""

    meta_parts = []
    if album["date_str"]:
        meta_parts.append(album["date_str"])
    if album["camera_str"]:
        meta_parts.append(album["camera_str"])
    subtitle_extra = " &nbsp;·&nbsp; ".join(meta_parts)

    notes_html = ""
    if album["notes"]:
        notes_html = f'<div class="album-notes">{album["notes"]}</div>'

    body = f"""
<a class="back" href="/index.html">
  <i class="fa-solid fa-arrow-left"></i> Gallery
</a>
<h1>{album['name']}</h1>
<p class="subtitle">{len(album['photos'])} photos{'&nbsp;&nbsp;·&nbsp;&nbsp;' + subtitle_extra if subtitle_extra else ''}</p>
{notes_html}
<div class="photo-masonry">{photos_html}</div>
<div class="lightbox" id="lightbox">
  <button class="lightbox-close" id="lb-close"><i class="fa-solid fa-xmark"></i></button>
  <button class="lightbox-nav lightbox-prev" id="lb-prev"><i class="fa-solid fa-chevron-left"></i></button>
  <button class="lightbox-nav lightbox-next" id="lb-next"><i class="fa-solid fa-chevron-right"></i></button>
  <img id="lb-img" src="" alt="">
  <span class="lightbox-caption" id="lb-cap"></span>
</div>"""

    out = OUTPUT_DIR / "albums" / f"{album['slug']}.html"
    out.write_text(base_html(album["name"], "gallery", body, LIGHTBOX_JS))
    print(f"[BUILD] albums/{album['slug']}.html")

def gear_md_to_list_html(path: Path) -> str:
    """Convert gear.md to gear-list HTML with .gcat / .grow rows instead of cards."""
    if not path.exists():
        return "<p>Edit <code>context/gear.md</code> to list your gear.</p>"

    html = ""
    in_list = False
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("## "):
            if in_list:
                html += "</div>\n"
                in_list = False
            html += f'<div class="gcat">{s[3:]}</div>\n'
        elif s.startswith("- "):
            item = s[2:]
            # Split "**Name** — description" into name + desc
            import re as _re
            m = _re.match(r"\*\*(.+?)\*\*\s*[-—]\s*(.*)", item)
            if m:
                name, desc = m.group(1), m.group(2)
            else:
                name, desc = item.replace("**", ""), ""
            html += f'<div class="grow"><span class="grn">{name}</span><span class="grd">{desc}</span></div>\n'
    return html

def build_gear():
    about_file  = CONTEXT_DIR / "about.md"
    gear_file   = CONTEXT_DIR / "gear.md"
    photo_src   = CONTEXT_DIR / "me.jpg"
    photo_dst   = OUTPUT_DIR  / "me.jpg"

    about_html = read_md(about_file)
    if not about_html:
        about_html = "<p>Edit <code>context/about.md</code> to update this section.</p>"

    gear_list_html = gear_md_to_list_html(gear_file)

    copy_asset(photo_src, photo_dst)
    photo_exists = photo_dst.exists()

    photo_block = ""
    if photo_exists:
        photo_block = f'<div class="about-photo-wrap"><img src="/me.jpg" alt="{SITE_AUTHOR}"></div>'

    body = f"""
<div class="gear-page">
  <h1 class="gear-page-title">My gear &amp; me</h1>
  <div class="gear-about">
    {photo_block}
    {about_html}
  </div>
  <div class="gear-list">
    {gear_list_html}
  </div>
</div>"""

    (OUTPUT_DIR / "gear.html").write_text(base_html("My gear & me", "gear", body))
    print("[BUILD] gear.html")

# --- Assets ------------------------------------------------------------------

def copy_photos_and_thumbs(albums):
    for album in albums:
        dest         = OUTPUT_DIR / "photos"   / album["slug"]
        preview_dest = OUTPUT_DIR / "previews" / album["slug"]
        thumb_dir    = OUTPUT_DIR / "thumbs"   / album["slug"]
        ensure_dir(dest)
        ensure_dir(preview_dest)
        ensure_dir(thumb_dir)

        cover_thumb = thumb_dir / "cover.jpg"
        if not cover_thumb.exists():
            print(f"[THUMB]   {album['name']} cover...")
            try:
                make_thumbnail(album["thumbnail"], cover_thumb)
            except Exception as e:
                print(f"[WARN]    Thumbnail failed: {e}")
                shutil.copy(album["thumbnail"], cover_thumb)

        new_count     = 0
        preview_count = 0
        for photo in album["photos"]:
            # Original (only copied, not resized)
            dst = dest / photo.name
            if not dst.exists():
                shutil.copy(photo, dst)
                new_count += 1

            # Preview (resized for masonry display)
            preview_dst = preview_dest / photo.name
            if not preview_dst.exists():
                try:
                    make_preview(photo, preview_dst)
                    preview_count += 1
                except Exception as e:
                    print(f"[WARN]    Preview failed for {photo.name}: {e}")
                    shutil.copy(photo, preview_dst)

        print(f"[COPY]    {album['name']}: {len(album['photos'])} photos "
              f"({new_count} new originals, {preview_count} new previews)")

# --- Main --------------------------------------------------------------------

def main():
    print(f"\n{'='*50}")
    print(f"  Purrfolio builder")
    print(f"  Photos  : {PHOTOS_DIR.resolve()}")
    print(f"  Output  : {OUTPUT_DIR.resolve()}")
    print(f"  Context : {CONTEXT_DIR.resolve()}")
    print(f"{'='*50}\n")

    ensure_dir(OUTPUT_DIR)
    ensure_dir(OUTPUT_DIR / "albums")
    ensure_dir(OUTPUT_DIR / "photos")
    ensure_dir(OUTPUT_DIR / "previews")
    ensure_dir(OUTPUT_DIR / "thumbs")

    albums = scan_albums()
    print(f"\n{len(albums)} album(s) found\n")

    copy_photos_and_thumbs(albums)

    print()
    build_index(albums)
    for a in albums:
        build_album(a)
    build_gear()

    print(f"\nDone. Site written to {OUTPUT_DIR.resolve()}")
    print(f"  {len(albums)} albums, {sum(len(a['photos']) for a in albums)} photos total\n")

if __name__ == "__main__":
    main()
