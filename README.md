# SimTagger

Updates the `simType` field in Microsoft Flight Simulator addon `manifest.json` files using a feed of accepted addons, and optionally moves entire airport folders to a new location while preserving the country/airport structure.

## Features
- Matches installed addons by `(ICAO, version)` against a JSON feed.
- Sets `simType` to an accepted tag (default `MSFS 2020/2024`).
- Dry run by default: previews updates and moves.
- Apply mode moves the whole addon folder, not just `manifest.json`.
- Preserves relative structure (e.g., `Asia\China\...`).
- Cross-drive free-space preflight with configurable safety margin.
- Dual logging: console and `logs/addsimtype_<timestamp>.log`.

## Requirements
- Python 3.8+
- Install dependencies:
  - `pip install -r requirements.txt`

## Configuration
You can set paths and behavior via `.env` or CLI flags. CLI flags override `.env`.

### .env file
Create a `.env` in the project root (or copy `.env.example`):

```
ADDONS_ROOT=E:\MFS2020 Addons\Airports
FEED_ROOT=Z:\projects\sceneryRSS
DEST_ROOT=E:\MFS2020&2024 Addons\Airports
SPACE_MARGIN_BYTES=262144000
ACCEPTED_TAG=MSFS 2020/2024
```

### CLI flags
- `--addons-root <path>`: Root folder containing installed airport addons.
- `--feed-root <path>`: Folder with feed JSON files.
- `--dest-root <path>`: Destination root for moved airports.
- `--space-margin-bytes <int>`: Extra bytes required beyond folder size for cross-drive moves (default 250 MiB).
- `--accepted-tag <string>`: Tag to set and use for move eligibility (default `MSFS 2020/2024`).
- `--apply`: Apply changes (update manifest and move folders). Without this, it runs a dry run.

Environment variables of the same names can be used instead of a `.env` file.

## Usage

### Dry run (preview only)
```
python simtagger.py
```
Shows `WILL_UPDATE` and `WILL_MOVE` lines, plus summary. No file changes.

### Apply changes (“wet” run)
```
python simtagger.py --apply
```
Updates `simType` and moves eligible airports (tag matches `ACCEPTED_TAG`).

### Specify paths explicitly
```
python simtagger.py \
  --addons-root "E:\\MFS2020 Addons\\Airports" \
  --feed-root   "Z:\\projects\\sceneryRSS" \
  --dest-root   "E:\\MFS2020&2024 Addons\\Airports"
```

### Move a single airport (safe test)
```
python simtagger.py --apply --addons-root "E:\\MFS2020 Addons\\Airports\\Africa\\Algeria\\simsoft-airport-dabc-mohamed-boudiaf"
```

## How it decides what to update/move
- Extracts ICAO from the folder name or manifest title.
- Normalizes version from `package_version` and feed title.
- If `(ICAO, version)` exists in the feed with `ACCEPTED_TAG`, the addon is eligible.
- Updates `simType` if needed; moves the whole folder if `ACCEPTED_TAG` matches.

## Move behavior
- Same-drive: fast rename; no space check required. Output shows `(rename)`.
- Cross-drive: copy+delete. Preflights free space using folder size + margin.
  - Dry run: `WILL_NO_SPACE` if insufficient.
  - Apply: `NO_SPACE` and skip if insufficient.
- Preserves relative structure from `ADDONS_ROOT` under `DEST_ROOT`.
- If destination already exists: `SKIP_EXIST`/`WILL_SKIP_EXIST` and no overwrite.

## Logging
- All output is mirrored to `logs/simtagger_<timestamp>.log`.

## Tips
- Start with a dry run and review the summary.
- Use the single-airport apply run for a safe first test.
- Adjust `SPACE_MARGIN_BYTES` if your destination drive is tight.

## Example feed item
Feed files are JSON arrays or objects with an `items` list. Example record:
```
{
  "title": "VTBU Rayong v1.2",
  "description": "Scenery package for Thailand. ICAO: VTBU",
  "page_url": "https://example.com/scenery/vtbu-rayong",
  "tag": "MSFS 2020/2024"
}
```

Place feed JSON in `FEED_ROOT`; the script will index all `*.json` files.# simtagger
