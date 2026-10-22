# Purrfolio

A minimal, self-hosted photography portfolio. Drop a folder of photos on your server, run one command, and the site builds itself.

Since 2.0 it looks like a proper portfolio: a full-screen hero with the latest album, an editorial album grid, justified photo rows, a full-screen viewer with EXIF details, and Catppuccin light/dark themes with self-hosted Inter and Fraunces fonts.

No CMS, no database, no framework. A Python script scans a directory of photo albums and outputs plain HTML served by Nginx.

## How it works

`build.py` scans `PHOTOS_DIR` for subdirectories. Each subdirectory becomes an album. `cover.jpg` (or the first photo) is the cover; photos are shown in filename order. Running `./build.sh` builds the Docker image and runs the generator, which writes the site into `output/`. Nginx picks that up immediately.

Pages:

- **Home** — full-screen hero with the newest album, a short intro (`context/intro.md`) and all albums as cards
- **Album** — title, date, camera and notes, then the photos in justified rows; click for a full-screen viewer with swipe, keyboard navigation, EXIF (camera, lens, focal length, aperture, shutter, ISO) and a link to the original. `#photo-5` links straight to a photo
- **About & gear** — `context/about.md` and `context/gear.md`, with `context/me.jpg` as portrait if present

Rebuilds are incremental: resized images are only regenerated when the source photo is newer, and EXIF is cached in `output/.cache/meta.json`. A rebuild without changes takes well under a second. Albums that disappear from `PHOTOS_DIR` are removed from the site.

## Requirements

- Docker and Docker Compose

## Installation

```bash
git clone https://github.com/Malse-Makker/purrfolio.git
cd purrfolio
cp .env.example .env
nano .env
```

Set at minimum:

```bash
SITE_TITLE=Your Name Photography
SITE_AUTHOR=Your Name
PHOTOS_DIR=/path/to/your/photo/albums
INSTAGRAM_URL=https://www.instagram.com/yourhandle/
```

Start Nginx and run the first build:

```bash
docker compose up -d nginx
./build.sh
```

The site is available on port 8081.

## Directory structure

```
Purrfolio/
├── context/
│   ├── intro.md          # one-line intro on the homepage
│   ├── about.md          # your bio shown on the gear page
│   ├── gear.md           # your gear list
│   └── me.jpg            # your photo shown next to the bio (optional)
├── output/               # generated site, served by Nginx (do not edit)
├── build.py              # the generator
├── build.sh              # run this to rebuild the site (Docker)
├── preview.sh            # build + serve locally on http://localhost:8090
├── static/               # site.css, site.js, fonts (copied to output/assets)
├── tools/fetch-sample.sh # copy downscaled real albums from the server for previews
├── docker-compose.yml
├── nginx.conf
├── Dockerfile
└── .env                  # your local config (not committed)
```

## Adding a new album

Create a folder inside your photos directory, put photos in it, then rebuild:

```bash
mkdir -p /mnt/storagebox/yourname/Iceland\ 2024
rsync -avz ./local-photos/ /mnt/storagebox/yourname/Iceland\ 2024/
./build.sh
```

## Album notes

Add a `notes.md` file inside any album folder to show a description above the photos:

```
photos/
└── Iceland 2024/
    ├── notes.md
    ├── IMG_001.jpg
    └── IMG_002.jpg
```

Supported Markdown: headings (`##`, `###`), paragraphs, `**bold**`, `*italic*`, links and `- lists`.

Optional meta lines in `notes.md` (removed from the text):

```
title: Perseids 2026          # display name, default: folder name with dashes as spaces
date: 12-08-2026              # default: EXIF date of the photos, then the folder date
camera: Nikon Z6 II           # default: from EXIF
thumb_position: top           # crop focus of the cover: top|center|bottom|left|right
```

Example:

```markdown
## Iceland, August 2024

Shot along the south coast and the Westfjords over two weeks.

**Camera:** Sony A7 IV
**Lenses:** 16-35mm f/2.8, 85mm f/1.8
```

## About and gear pages

Edit the files in the `context/` folder:

- `context/about.md` — bio shown on the gear page, next to your photo
- `context/gear.md` — gear list, supports headings and `- bullet` lists
- `context/me.jpg` — your photo, shown next to the bio (optional, any name works as long as it is `me.jpg`)

Run `./build.sh` after any change.

## Watermark

Every photo inside an album (grid, full-screen viewer and the original download) gets `brand/watermark.png` in white at 60% opacity, centred at the bottom, about 15% of the photo's long side wide. Album covers on the home page stay clean. The source photos in `PHOTOS_DIR` are never changed; the originals offered for download are watermarked copies that keep their EXIF.

To change the mark, replace `brand/watermark.png` (white on transparent) and rebuild: the build notices the new file and regenerates every image once. Set `WATERMARK` to a path that does not exist to switch it off.

## Previewing locally

```bash
./tools/fetch-sample.sh   # once: downscaled copy of the real albums (~80 MB)
./preview.sh              # build into preview-output/ and serve on http://localhost:8090
```

`preview.sh` uses a local Python with Pillow, `nix-shell`, or the Docker image, whichever is available.

## Uploading photos from another machine

```bash
rsync -avz ./local-photos/ user@yourserver:/mnt/storagebox/yourname/Iceland\ 2024/
ssh user@yourserver "cd ~/Purrfolio && ./build.sh"
```

## Nginx Proxy Manager

Add a new proxy host pointing to the `purrfolio-nginx` container on port 80. Enable SSL via Let's Encrypt.

## Configuration reference

| Variable       | Description                                             |
|----------------|---------------------------------------------------------|
| SITE_TITLE     | Name shown in the navigation bar                        |
| SITE_AUTHOR    | Name shown in the footer                                |
| PHOTOS_DIR     | Absolute path to the folder containing your albums      |
| OUTPUT_DIR     | Path where the generated site is written                |
| INSTAGRAM_URL  | Full Instagram URL, shown in the footer (optional)      |
| WATERMARK      | Watermark image (default `brand/watermark.png`)         |

## License

MIT — free to use, modify, and share.

---

Purrfolio is part of the **makkers collection** — a set of free, open-source hobby projects built and hosted at [projecten.makkers.net](https://projecten.makkers.net). Non-commercial, made for fun and learning.

---

*This project was built with the help of AI as a personal play and learning project — to learn more about AI and about building self-hosted tools. The CI/CD pipeline (automatic deployment via GitHub Actions) is part of that learning process too.*
