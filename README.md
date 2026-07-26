# Purrfolio

A minimal, self-hosted photography portfolio. Drop a folder of photos on your server, run one command, and the site builds itself.

No CMS, no database, no framework. A Python script scans a directory of photo albums and outputs plain HTML served by Nginx.

## How it works

`build.py` scans `PHOTOS_DIR` for subdirectories. Each subdirectory becomes an album on the gallery page. The first photo in each album is used as the cover thumbnail. Running `./build.sh` builds the Docker image and runs the generator, which writes the site into `output/`. Nginx picks that up immediately.

The site has two pages: a gallery with a masonry layout and a "My gear & me" page. There is a theme switcher in the nav for light, dark, and Catppuccin themes.

## Requirements

- Docker and Docker Compose

## Installation

```bash
git clone https://github.com/Nijntje94/Purrfolio.git
cd Purrfolio
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
│   ├── about.md          # your bio shown on the gear page
│   ├── gear.md           # your gear list
│   └── me.jpg            # your photo shown next to the bio (optional)
├── output/               # generated site, served by Nginx (do not edit)
├── build.py              # the generator
├── build.sh              # run this to rebuild the site
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

Supported Markdown: headings (`##`, `###`), paragraphs, `**bold**`, `*italic*`, and `- lists`.

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

## License

MIT — free to use, modify, and share.

---

Purrfolio is part of the **makkers collection** — a set of free, open-source hobby projects built and hosted at [projecten.makkers.net](https://projecten.makkers.net). Non-commercial, made for fun and learning.

---

*This project was built with the help of AI as a personal play and learning project — to learn more about AI and about building self-hosted tools. The CI/CD pipeline (automatic deployment via GitHub Actions) is part of that learning process too.*
