#!/usr/bin/env python3
"""
Purrfolio - static site generator
Scans the photos directory and outputs a plain HTML site into the output directory.
"""

import os
import re
import shutil
from pathlib import Path
from PIL import Image

# --- Configuration -----------------------------------------------------------

PHOTOS_DIR    = Path(os.environ.get("PHOTOS_DIR", "./photos"))
OUTPUT_DIR    = Path(os.environ.get("OUTPUT_DIR", "./output"))
CONTEXT_DIR   = Path(os.environ.get("CONTEXT_DIR", "./context"))
SITE_TITLE    = os.environ.get("SITE_TITLE", "My Portfolio")
SITE_AUTHOR   = os.environ.get("SITE_AUTHOR", "Photographer")
INSTAGRAM_URL = os.environ.get("INSTAGRAM_URL", "")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
THUMB_SIZE = (600, 400)

# --- Helpers -----------------------------------------------------------------

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def is_image(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("._")

def make_thumbnail(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Copy to a temp local file first to avoid xattr errors on remote mounts
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=src.suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copy(src, tmp_path)
        with Image.open(tmp_path) as img:
            img = img.convert("RGB")
            img.thumbnail((THUMB_SIZE[0] * 2, THUMB_SIZE[1] * 2), Image.LANCZOS)
            w, h = img.size
            tw, th = THUMB_SIZE
            left = (w - tw) // 2
            top  = (h - th) // 2
            img  = img.crop((left, top, left + tw, top + th))
            img.save(dst, "JPEG", quality=82, optimize=True)
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
            html += f"<li>{item}</li>\n"
        else:
            if in_list: html += "</ul>\n"; in_list = False
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         line)
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
    """Parse notes.md, extract date: and camera: meta lines, return (sort_key, date_str, camera_str, html)."""
    date_override   = None
    camera_override = None
    if notes_path.exists():
        lines     = notes_path.read_text(encoding="utf-8").splitlines()
        kept      = []
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
            else:
                kept.append(line)
        notes_html = md_to_html("\n".join(kept))
    else:
        notes_html = ""
    return date_override, camera_override, notes_html

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
        date_override, camera_override, notes_html = parse_notes(notes_path)

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

        albums.append({
            "name":       album_dir.name,
            "slug":       slugify(album_dir.name),
            "dir":        album_dir,
            "photos":     photos,
            "thumbnail":  photos[0],
            "notes":      notes_html,
            "date_str":   date_str,
            "sort_key":   sort_key,
            "camera_str": camera_str,
        })
        has_notes = "yes" if notes_path.exists() else "no"
        print(f"[OK]   {album_dir.name}: {len(photos)} photo(s), date: {date_str or 'none'}, camera: {camera_str or 'none'}")

    # Sort newest first
    albums.sort(key=lambda a: a["sort_key"], reverse=True)
    return albums

# --- HTML templates ----------------------------------------------------------

THEME_CSS = """
html,body{--bg:#fff;--bg2:#f5f5f0;--text:#1a1a1a;--text2:#666;--accent:#1a1a1a;--border:rgba(0,0,0,.1);--card:#fff}
html.theme-dark,html.theme-dark body{--bg:#1a1a1a;--bg2:#242424;--text:#e8e8e0;--text2:#aaa;--accent:#e8e8e0;--border:rgba(255,255,255,.1);--card:#2a2a2a}
html.theme-cat,html.theme-cat body{--bg:#303446;--bg2:#292c3c;--text:#c6d0f5;--text2:#a5adce;--accent:#ca9ee6;--border:rgba(198,208,245,.15);--card:#363a4f}
"""

THEME_INLINE = """
(function(){
  var t=localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  document.documentElement.className=t==='light'?'':'theme-'+t;
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
.gallery-item img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .4s ease}
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
.gear-section-title{font-size:11px;font-weight:500;color:var(--text2);letter-spacing:.08em;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.gear-md h2{font-size:13px;font-weight:500;color:var(--text2);letter-spacing:.06em;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border);margin-top:28px}
.gear-md h2:first-child{margin-top:0}
.gear-md h3{font-size:13px;font-weight:500;color:var(--text);margin-bottom:8px;margin-top:16px}
.gear-md ul{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:8px}
.gear-md li{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 14px;font-size:13px;color:var(--text2)}
.gear-md li strong{color:var(--text);display:block;margin-bottom:2px}
.gear-md p{font-size:13px;color:var(--text2);margin-bottom:6px}
footer{text-align:center;font-size:11px;color:var(--text2);padding:28px 0;border-top:1px solid var(--border);margin-top:48px;letter-spacing:.05em}
footer a{color:var(--text2);text-decoration:none;border-bottom:1px solid var(--border);transition:color .2s,border-color .2s;padding-bottom:1px}
footer a:hover{color:var(--text);border-color:var(--text)}
@media(max-width:520px){.about-layout{flex-direction:column}.about-photo{width:100%}}
"""

THEME_JS = """
const THEMES = ['light','dark','cat'];
const btns = document.querySelectorAll('.theme-btn');
function applyTheme(t) {
  document.documentElement.className = t === 'light' ? '' : 'theme-' + t;
  btns.forEach((b,i) => b.classList.toggle('active', THEMES[i] === t));
  localStorage.setItem('theme', t);
}
btns.forEach((b, i) => b.addEventListener('click', () => applyTheme(THEMES[i])));
const saved = localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
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

def footer_html() -> str:
    parts = [f"&copy; {SITE_AUTHOR}"]
    if INSTAGRAM_URL:
        parts.append(f'<a href="{INSTAGRAM_URL}" target="_blank" rel="noopener"><i class="fa-brands fa-instagram"></i> Instagram</a>')
    parts.append(f'site made by <a href="https://github.com/Nijntje94/Purrfolio" target="_blank" rel="noopener">Purrfolio</a>')
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
    <button class="theme-btn" title="Light" aria-label="Light theme"><i class="fa-solid fa-sun"></i></button>
    <button class="theme-btn" title="Dark" aria-label="Dark theme"><i class="fa-solid fa-moon"></i></button>
    <button class="theme-btn" title="Catppuccin" aria-label="Catppuccin theme"><i class="fa-solid fa-cat"></i></button>
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
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" crossorigin="anonymous">
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

def gallery_grid_css(n: int) -> str:
    """Generate grid-template CSS for n albums using layout A pattern."""
    if n == 1:
        return "grid-template-columns:1fr;grid-template-rows:400px"
    if n == 2:
        return "grid-template-columns:1fr 1fr;grid-template-rows:360px"
    # Groups of 3: featured wide + tall + small, repeating
    rows = []
    col_def = "grid-template-columns:1fr 1fr 1fr"
    row_heights = []
    i = 0
    while i < n:
        remaining = n - i
        if remaining == 1:
            row_heights.append("160px")
            i += 1
        elif remaining == 2:
            row_heights.append("160px")
            i += 2
        else:
            row_heights.append("260px")
            row_heights.append("160px")
            i += 3
    return f"{col_def};grid-template-rows:{' '.join(row_heights)}"

def gallery_item_style(i: int, n: int) -> str:
    """Return grid-column/row placement for album at index i."""
    if n == 1:
        return ""
    if n == 2:
        return ""
    # Pattern per group of 3: item0=wide(col1-3,row1), item1=tall(col3,row1-2), item2=small(col1,row2), item3=small(col2,row2)
    # Then repeats with new rows
    group = i // 3
    pos   = i % 3
    # Each group occupies 2 rows
    base_row = group * 2 + 1
    if pos == 0:
        return f"grid-column:1/3;grid-row:{base_row}"
    elif pos == 1:
        return f"grid-column:3;grid-row:{base_row}/{base_row+2}"
    else:
        # pos==2: check if there's a pos==3 in same group
        next_i = i + 1
        if next_i < n and next_i % 3 == 0:
            # no pos3, this one spans
            return f"grid-column:1/3;grid-row:{base_row+1}"
        return f"grid-column:1;grid-row:{base_row+1}"
    return ""

def build_index(albums):
    n = len(albums)
    items = ""
    for i, a in enumerate(albums):
        thumb_path = f"thumbs/{a['slug']}/cover.jpg"
        count = len(a['photos'])
        meta = f"{count} photo{'s' if count != 1 else ''}"
        if a['date_str']:
            meta += f" &nbsp;·&nbsp; {a['date_str']}"
        style = gallery_item_style(i, n)
        style_attr = f' style="{style}"' if style else ""
        loading = "eager" if i < 3 else "lazy"
        items += f"""
<a class="gallery-item" href="/albums/{a['slug']}.html"{style_attr}>
  <img src="/{thumb_path}" alt="{a['name']}" loading="{loading}">
  <div class="gallery-overlay">
    <div class="album-name">{a['name']}</div>
    <div class="album-meta">{meta}</div>
  </div>
</a>"""

    grid_css = gallery_grid_css(n)
    body = f"""
<h1>Gallery</h1>
<p class="subtitle">{n} album{'s' if n != 1 else ''}</p>
<div class="gallery-grid" style="{grid_css}">{items}</div>"""

    (OUTPUT_DIR / "index.html").write_text(base_html("Gallery", "gallery", body))
    print("[BUILD] index.html")

def build_album(album):
    photos_html = ""
    for i, p in enumerate(album["photos"]):
        web_path = f"/photos/{album['slug']}/{p.name}"
        photos_html += f"""
<div class="photo-item" data-src="{web_path}" data-caption="{p.stem}">
  <img src="{web_path}" alt="{p.stem}" loading="{'eager' if i < 6 else 'lazy'}">
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

def build_gear():
    about_file  = CONTEXT_DIR / "about.md"
    gear_file   = CONTEXT_DIR / "gear.md"
    photo_src   = CONTEXT_DIR / "me.jpg"
    photo_dst   = OUTPUT_DIR  / "me.jpg"

    about_html = read_md(about_file)
    if not about_html:
        about_html = "<p>Edit <code>context/about.md</code> to update this section.</p>"

    gear_html = read_md(gear_file)
    if not gear_html:
        gear_html = "<p>Edit <code>context/gear.md</code> to list your gear.</p>"

    copy_asset(photo_src, photo_dst)
    photo_exists = photo_dst.exists()

    if photo_exists:
        about_block = f"""
<div class="about-layout">
  <div class="about-photo"><img src="/me.jpg" alt="{SITE_AUTHOR}"></div>
  <div class="about-text">{about_html}</div>
</div>"""
    else:
        about_block = f'<div class="about-text" style="max-width:640px;margin-bottom:40px;padding-bottom:32px;border-bottom:1px solid var(--border)">{about_html}</div>'

    body = f"""
<h1>My gear &amp; me</h1>
{about_block}
<div class="gear-md">{gear_html}</div>"""

    (OUTPUT_DIR / "gear.html").write_text(base_html("My gear & me", "gear", body))
    print("[BUILD] gear.html")

# --- Assets ------------------------------------------------------------------

def copy_photos_and_thumbs(albums):
    for album in albums:
        dest = OUTPUT_DIR / "photos" / album["slug"]
        ensure_dir(dest)
        thumb_dir = OUTPUT_DIR / "thumbs" / album["slug"]
        ensure_dir(thumb_dir)

        cover_thumb = thumb_dir / "cover.jpg"
        if not cover_thumb.exists():
            print(f"[THUMB] {album['name']} cover...")
            try:
                make_thumbnail(album["thumbnail"], cover_thumb)
            except Exception as e:
                print(f"[WARN]  Thumbnail failed: {e}")
                shutil.copy(album["thumbnail"], cover_thumb)

        for photo in album["photos"]:
            dst = dest / photo.name
            if not dst.exists():
                shutil.copy(photo, dst)

        print(f"[COPY]  {album['name']}: {len(album['photos'])} photos")

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
