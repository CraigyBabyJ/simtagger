#!/usr/bin/env python3


"""
simtagger.py — Updates the 'simType' field in Microsoft Flight Simulator addon manifest.json files.

This script compares installed MSFS addon packages (specifically those with a manifest.json)
against a "feed" of known and accepted addons. It extracts ICAO codes and version information
from both the addon's folder name/manifest and the feed data.

If a match is found in the feed for an installed addon, and its 'simType' field in
manifest.json is missing or different, the script proposes to update it to the
'ACCEPTED_TAG' (e.g., "MSFS 2020/2024").

Key features:
- Reads manifest.json files from a specified ADDONS_ROOT directory.
- Loads a feed of accepted addons from JSON files in a FEED_ROOT directory.
- Extracts ICAO codes from folder names (e.g., "...-vtbu-...") or manifest titles.
- Extracts version information from manifest files and feed titles.
- Performs a dry run by default, showing proposed changes.
- Applies changes (modifies manifest.json files) only when the `--apply` argument is provided.
- Logs all output (console and errors) to a timestamped log file in a 'logs' directory.
- Reports on files with bad JSON, missing version info, or no matching feed entry.
"""
import os, re, json, sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import atexit
import shutil
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args, **kwargs):
        return False

# ========= Dual output: console + log (robust) =========
# Capture the original streams *before* we replace them.
old_stdout = sys.stdout
old_stderr = sys.stderr

class _Tee:
    def __init__(self, *targets):
        self.targets = targets
    def write(self, data):
        for t in self.targets:
            try:
                t.write(data)
            except Exception:
                pass
        self.flush()
    def flush(self):
        for t in self.targets:
            try:
                t.flush()
            except Exception:
                pass

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"simtagger_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
_LOG_FP = open(LOG_FILE, "a", encoding="utf-8")

def _close_log():
    try:
        print(f"=== Run finished {datetime.now().isoformat(timespec='seconds')} ===")
        _LOG_FP.flush()
        _LOG_FP.close()
    except Exception:
        pass

atexit.register(_close_log)

# Duplicate prints/tracebacks to BOTH the original console and the log file.
sys.stdout = _Tee(old_stdout, _LOG_FP)
sys.stderr = _Tee(old_stderr, _LOG_FP)

def _print_banner():
    banner = r"""
  ____  _           _                             
 / ___|| |_ ___  __| | ___  __ _  __ _  ___ _ __  
 \___ \| __/ _ \/ _` |/ _ \/ _` |/ _` |/ _ \ '_ \ 
  ___) | ||  __/ (_| |  __/ (_| | (_| |  __/ | | |
 |____/ \__\___|\__,_|\___|\__,_|\__, |\___|_| |_|
                               |___/              
 SIMTAGGER
    """
    print(banner)

_print_banner()
print(f"=== Run started  {datetime.now().isoformat(timespec='seconds')} ===")
print("Args:", " ".join(sys.argv))
print("Log file:", LOG_FILE)

print("Initializing paths …")
try:
    # Load environment from .env if present (non-fatal if missing)
    load_dotenv()
    print("Loaded .env (if present)")
except Exception:
    pass

# ---------------------------
# Hardcoded paths (match your logs)
# ---------------------------
DEFAULT_ADDONS_ROOT = Path(r"E:\MFS2020 Addons\Airports")
DEFAULT_FEED_ROOT   = Path(r"Z:\projects\sceneryRSS")
DEFAULT_DEST_ROOT   = Path(r"E:\MFS2020&2024 Addons\Airports")
DEFAULT_SPACE_MARGIN_BYTES = 250 * 1024 * 1024  # 250 MiB safety margin
DEFAULT_ACCEPTED_TAG = "MSFS 2020/2024"

def _arg_or_env_path(flag: str, env_name: str, default: Path) -> Path:
    val = None
    for i, a in enumerate(sys.argv):
        if a.startswith(flag+"="):
            val = a.split("=",1)[1]
            break
        if a == flag and i+1 < len(sys.argv):
            val = sys.argv[i+1]
            break
    if not val:
        val = os.environ.get(env_name)
    return Path(val) if val else default

def _arg_or_env_int(flag: str, env_name: str, default: int) -> int:
    val = None
    for i, a in enumerate(sys.argv):
        if a.startswith(flag+"="):
            val = a.split("=",1)[1]
            break
        if a == flag and i+1 < len(sys.argv):
            val = sys.argv[i+1]
            break
    if not val:
        val = os.environ.get(env_name)
    try:
        return int(val) if val is not None else default
    except Exception:
        return default

def _arg_or_env_str(flag: str, env_name: str, default: str) -> str:
    val = None
    for i, a in enumerate(sys.argv):
        if a.startswith(flag+"="):
            val = a.split("=",1)[1]
            break
        if a == flag and i+1 < len(sys.argv):
            val = sys.argv[i+1]
            break
    if not val:
        val = os.environ.get(env_name)
    return val if val is not None and val != "" else default

ADDONS_ROOT = _arg_or_env_path("--addons-root", "ADDONS_ROOT", DEFAULT_ADDONS_ROOT)
FEED_ROOT   = _arg_or_env_path("--feed-root",   "FEED_ROOT",   DEFAULT_FEED_ROOT)
DEST_ROOT   = _arg_or_env_path("--dest-root",   "DEST_ROOT",   DEFAULT_DEST_ROOT)
SPACE_MARGIN_BYTES = _arg_or_env_int("--space-margin-bytes", "SPACE_MARGIN_BYTES", DEFAULT_SPACE_MARGIN_BYTES)
ACCEPTED_TAG = _arg_or_env_str("--accepted-tag", "ACCEPTED_TAG", DEFAULT_ACCEPTED_TAG)

print(f"Roots: addons={ADDONS_ROOT} | feed={FEED_ROOT} | dest={DEST_ROOT}")
print(f"Space margin: {SPACE_MARGIN_BYTES} bytes")
print(f"Accepted tag: {ACCEPTED_TAG}")

def same_drive(a: Path, b: Path) -> bool:
    try:
        return a.drive.upper() == b.drive.upper()
    except Exception:
        return True  # assume same when uncertain

def directory_size_bytes(dir_path: Path) -> int:
    total = 0
    # Walk files; skip directories
    for p in dir_path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except Exception:
            # ignore unreadable entries
            pass
    return total

def human_bytes(n: int) -> str:
    # Simple IEC units
    for unit in ("bytes","KiB","MiB","GiB","TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}" if unit != "bytes" else f"{n} bytes"
        n /= 1024
    return f"{n:.1f} TiB"

# ---------------------------
# Regex helpers
# ---------------------------
RE_VERSION_IN_TITLE = re.compile(r"(?:^|[\s\-_])v?(\d+(?:[.\-_]\d+){0,3})(?:\b|$)", re.IGNORECASE)
RE_ICAO_IN_DESC     = re.compile(r"ICAO:\s*([A-Za-z]{4})", re.IGNORECASE)
RE_ANY_ICAO         = re.compile(r"\b([A-Za-z]{4})\b")
RE_FOLDER_ICAO      = re.compile(r"(?:^|[-_ ])([A-Za-z]{4})(?:$|[-_ ])")  # …-vtbu-… (case-insensitive)
RE_SLUG_ICAO        = re.compile(r"(?:^|[-_/])([a-z]{4})(?:[-_/]|$)", re.IGNORECASE)

def norm_version(v: str) -> Optional[Tuple[int,int,int]]:
    if not v: return None
    v = v.strip().lstrip("vV").replace("_",".").replace("-", ".")
    parts = [p for p in v.split(".") if p]
    try:
        nums = [int(p) for p in parts[:3]]
    except ValueError:
        return None
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])

def version_equal(a: str, b: str) -> bool:
    na, nb = norm_version(a), norm_version(b)
    return na is not None and nb is not None and na == nb

def normalize_version_string(v: str) -> Optional[str]:
    nv = norm_version(v)
    return ".".join(map(str, nv)) if nv else None

def extract_version_from_title(title: str) -> Optional[str]:
    m = RE_VERSION_IN_TITLE.search(title or "")
    return normalize_version_string(m.group(1)) if m else None

def find_icaos_in_entry(title: str, desc: str, page_url: str) -> List[str]:
    # 1) Prefer explicit "ICAO: XXXX" in description
    m = RE_ICAO_IN_DESC.search(desc or "")
    if m:
        return [m.group(1).upper()]
    # 2) Look in title for any 4-letter token (case-insensitive)
    t_found = {tok.upper() for tok in RE_ANY_ICAO.findall(title or "")}
    # 3) Also search page_url slug (often contains -vtbu- style)
    slug_found = {tok.upper() for tok in RE_SLUG_ICAO.findall(page_url or "")}
    found = list(sorted(t_found.union(slug_found)))
    return found

def folder_icao(folder_name: str) -> Optional[str]:
    m = RE_FOLDER_ICAO.search(folder_name or "")
    if not m: return None
    tok = m.group(1)
    return tok.upper() if tok and len(tok)==4 and tok.isalpha() else None

def manifest_icao_from_title(manifest_title: str) -> Optional[str]:
    for m in RE_ANY_ICAO.finditer(manifest_title or ""):
        tok = m.group(1)
        if len(tok) == 4 and tok.isalpha():
            return tok.upper()
    return None

# ---------------------------
# Feed indexing
# ---------------------------
class FeedItem:
    def __init__(self, source: Path, raw: dict):
        self.source = source
        self.title = (raw.get("title") or "").strip()
        self.description = (raw.get("description") or "").strip()
        self.page_url = (raw.get("page_url") or raw.get("link") or "").strip()
        self.tag = (raw.get("tag") or raw.get("category") or "").strip()
        self.version = extract_version_from_title(self.title)
        self.icaos = find_icaos_in_entry(self.title, self.description, self.page_url)

    def is_msfs(self) -> bool:
        return self.tag == ACCEPTED_TAG and self.version is not None and len(self.icaos) > 0

class FeedIndex:
    def __init__(self):
        # (ICAO, version) -> tag string
        self.index: Dict[Tuple[str, str], str] = {}

    def add_item(self, item: FeedItem):
        if not item.is_msfs():
            return
        for icao in item.icaos:
            key = (icao.upper(), item.version)
            self.index[key] = item.tag  # always store exact tag

def load_feed_index(feed_root: Path) -> FeedIndex:
    idx = FeedIndex()
    # Process files sorted by name so later files (typically newer) can override
    for fp in sorted(feed_root.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"ERROR reading {fp}: {e}")
            continue
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for raw in items:
            if not isinstance(raw, dict): continue
            item = FeedItem(fp, raw)
            if item.is_msfs():
                idx.add_item(item)
    return idx

# ---------------------------
# Main work
# ---------------------------
def main():
    apply = ("--apply" in sys.argv)
    if not ADDONS_ROOT.exists():
        print(f"ERROR: Addons root not found: {ADDONS_ROOT}")
        return
    if not FEED_ROOT.exists():
        print(f"ERROR: Feed root not found: {FEED_ROOT}")
        return
    # Destination root is created lazily when applying moves
    if apply and not DEST_ROOT.exists():
        try:
            DEST_ROOT.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"ERROR: Could not create destination root {DEST_ROOT}: {e}")
            return

    idx = load_feed_index(FEED_ROOT)
    print(f"Feed index loaded: {len(idx.index)} (ICAO,version) MSFS entries.")

    counts = {
        "will_update":0, "updated":0, "noop":0, "no_version":0, "no_match":0, "bad_json":0,
        "will_move":0, "moved":0, "skip_exist":0, "move_failed":0,
        "will_no_space":0, "no_space":0
    }
    bad_json_files = []  # collect for grouped summary

    # Collect manifests first to avoid interference when moving directories
    manifest_paths = list(ADDONS_ROOT.rglob("manifest.json"))
    for man_path in manifest_paths:
        folder_name = man_path.parent.name
        try:
            manifest = json.loads(man_path.read_text(encoding="utf-8"))
        except Exception as e:
            # inline console + log (kept)
            print(f"BAD_JSON    | {man_path} | {e}")
            counts["bad_json"] += 1
            bad_json_files.append(f"{man_path} | {e}")  # for grouped block
            continue

        man_version = (manifest.get("package_version") or "").strip()
        if not man_version:
            print(f"NO_VERSION  | {man_path}")
            counts["no_version"] += 1
            continue
        man_version_norm = normalize_version_string(man_version)
        if not man_version_norm:
            print(f"NO_VERSION  | {man_path}")
            counts["no_version"] += 1
            continue

        # Determine ICAO: prefer folder name pattern like ...-vtbu-...
        icao = folder_icao(folder_name)
        if not icao:
            # fallback to manifest title
            icao = manifest_icao_from_title(manifest.get("title","")) or None

        if not icao:
            print(f"NO_MATCH    | ???? | v{man_version} | {man_path}")
            counts["no_match"] += 1
            continue

        key = (icao.upper(), man_version_norm)
        tag = idx.index.get(key)
        if not tag:
            print(f"NO_MATCH    | {icao} | v{man_version_norm} | {man_path}")
            counts["no_match"] += 1
            continue

        before = manifest.get("simType")
        after  = tag  # exact tag from feed JSON, e.g., "MSFS 2020/2024"

        needs_update = (before != after)

        # Update simType or preview it
        if apply:
            if needs_update:
                manifest["simType"] = after
                man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"UPDATED     | {icao} | v{man_version_norm} | simType {before} -> {after} | {man_path}")
                counts["updated"] += 1
            else:
                print(f"NOOP        | {icao} | v{man_version_norm} | simType already {before} | {man_path}")
                counts["noop"] += 1
        else:
            if needs_update:
                print(f"WILL_UPDATE | {icao} | v{man_version_norm} | simType {before} -> {after} | {man_path}")
                counts["will_update"] += 1
            else:
                print(f"NOOP        | {icao} | v{man_version_norm} | simType already {before} | {man_path}")
                counts["noop"] += 1

        # Move airport folder when tagged for MSFS 2020/2024
        if after == ACCEPTED_TAG:
            src_dir = man_path.parent
            try:
                rel_subpath = src_dir.relative_to(ADDONS_ROOT)
            except Exception:
                rel_subpath = Path(src_dir.name)
            dest_dir = DEST_ROOT / rel_subpath

            # Determine move mode: rename (same drive) vs copy+delete (cross-drive)
            is_rename = same_drive(src_dir, DEST_ROOT)

            if apply:
                if dest_dir.exists():
                    print(f"SKIP_EXIST  | {icao} | v{man_version_norm} | dest exists | {dest_dir}")
                    counts["skip_exist"] += 1
                else:
                    # For cross-drive moves, preflight free space check
                    if not is_rename:
                        try:
                            size_bytes = directory_size_bytes(src_dir)
                            free_bytes = shutil.disk_usage(DEST_ROOT).free
                            required = size_bytes + SPACE_MARGIN_BYTES
                            if required > free_bytes:
                                print(
                                    f"NO_SPACE    | {icao} | v{man_version_norm} | required {human_bytes(required)} > free {human_bytes(free_bytes)} | {src_dir} -> {dest_dir}"
                                )
                                counts["no_space"] += 1
                                # Skip move
                                continue
                        except Exception:
                            # If space check fails, attempt move anyway
                            pass
                    try:
                        dest_dir.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src_dir), str(dest_dir))
                        mode = "rename" if is_rename else "copy+delete"
                        print(f"MOVED       | {icao} | v{man_version_norm} | ({mode}) {src_dir} -> {dest_dir}")
                        counts["moved"] += 1
                    except Exception as e:
                        print(f"MOVE_FAILED | {icao} | v{man_version_norm} | {src_dir} -> {dest_dir} | {e}")
                        counts["move_failed"] += 1
            else:
                if dest_dir.exists():
                    print(f"WILL_SKIP_EXIST | {icao} | v{man_version_norm} | dest exists | {dest_dir}")
                    counts["skip_exist"] += 1
                else:
                    if is_rename:
                        print(f"WILL_MOVE   | {icao} | v{man_version_norm} | (rename) {src_dir} -> {dest_dir}")
                        counts["will_move"] += 1
                    else:
                        # Pre-compute size and available space for preview
                        try:
                            size_bytes = directory_size_bytes(src_dir)
                            free_bytes = shutil.disk_usage(DEST_ROOT).free
                            required = size_bytes + SPACE_MARGIN_BYTES
                            if required > free_bytes:
                                print(
                                    f"WILL_NO_SPACE | {icao} | v{man_version_norm} | required {human_bytes(required)} > free {human_bytes(free_bytes)} | {src_dir} -> {dest_dir}"
                                )
                                counts["will_no_space"] += 1
                            else:
                                print(
                                    f"WILL_MOVE   | {icao} | v{man_version_norm} | (copy+delete, size {human_bytes(size_bytes)}, free {human_bytes(free_bytes)}, margin {human_bytes(SPACE_MARGIN_BYTES)}) {src_dir} -> {dest_dir}"
                                )
                                counts["will_move"] += 1
                        except Exception:
                            print(f"WILL_MOVE   | {icao} | v{man_version_norm} | (copy+delete) {src_dir} -> {dest_dir}")
                            counts["will_move"] += 1

    print("\nSummary:")
    print(f"  WILL_UPDATE: {counts['will_update']}")
    print(f"  UPDATED    : {counts['updated']}")
    print(f"  NOOP       : {counts['noop']}")
    print(f"  NO_VERSION : {counts['no_version']}")
    print(f"  NO_MATCH   : {counts['no_match']}")
    print(f"  BAD_JSON   : {counts['bad_json']}")
    print(f"  WILL_MOVE  : {counts['will_move']}")
    print(f"  MOVED      : {counts['moved']}")
    print(f"  SKIP_EXIST : {counts['skip_exist']}")
    print(f"  MOVE_FAIL  : {counts['move_failed']}")
    print(f"  WILL_NO_SPACE: {counts['will_no_space']}")
    print(f"  NO_SPACE     : {counts['no_space']}")

    if bad_json_files:
        print("\n==== BAD_JSON FILES (grouped) ====")
        for entry in bad_json_files:
            print(entry)
        print("=================================")

if __name__ == "__main__":
    main()
