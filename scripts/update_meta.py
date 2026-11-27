"""
Monthly data pipeline: downloads the latest Smogon stats for every registered format,
then rebuilds the files derived from them (topPoke.json, speed tiers).

Smogon posts a month's stats a few days into the next month, so the workflow runs on
several days. data/stats/manifest.json records which month is on disk, so runs after
a successful one exit early.

Usage:
  python scripts/update_meta.py                  # latest month, skip if already current
  python scripts/update_meta.py --month 2026-09  # a specific month
  python scripts/update_meta.py --force          # redownload even if current
  python scripts/update_meta.py --rebuild-index  # also rebuild the local RAG index (needs the ML deps)
"""
import argparse
import json
import logging
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from metamatch import config, scrapers  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
MANIFEST = config.STATS_DIR / "manifest.json"


def previous_month():
    first_current = datetime.today().replace(day=1)
    last_prev = first_current - timedelta(days=1)
    return f"{last_prev.year:04d}-{last_prev.month:02d}"


def read_manifest():
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def month_published(url):
    try:
        return requests.head(url, timeout=30, allow_redirects=True).status_code == 200
    except requests.RequestException:
        return False


def planned_downloads(month_url):
    """(index url, remote file, local file) for every file each format needs."""
    for fmt in config.FORMATS.values():
        yield month_url, fmt["stats"] + ".txt", fmt["stats"] + ".txt"
        yield month_url + "chaos/", fmt["stats"] + ".json", fmt["stats"] + ".json"
        if fmt["game"] == "champions":
            # Display names for the RAG usage cards (SV names already come from Smogon sets data)
            yield month_url + "moveset/", fmt["stats"] + ".txt", fmt["stats"] + ".moveset.txt"


def all_ratings(month_url, src_dir, dest_dir):
    """Writes <format>-allratings.json for every format: the rarely used Pokemon's sets from Smogon's all ratings
    stats (metamatch.auditor.trim_all_ratings), so a pick the top ladder never brings still gets a real set. A format
    whose file fails is skipped with a warning: the main stats are what the month needs."""
    from metamatch.auditor import all_ratings_path, trim_all_ratings
    for fid, fmt in config.FORMATS.items():
        base = fmt["stats"].rsplit("-", 1)[0]
        raw = f"{base}-0.json"
        if not scrapers.download_stat_file(month_url + "chaos/", raw, raw, dest_dir=dest_dir):
            logging.warning(f"Skipped the all ratings stats for {fid}")
            continue
        try:
            low = json.loads((dest_dir / raw).read_text(encoding="utf-8")).get("data", {})
            high = json.loads((src_dir / (fmt["stats"] + ".json")).read_text(encoding="utf-8")).get("data", {})
        except (OSError, ValueError) as e:
            logging.warning(f"Skipped the all ratings stats for {fid}: {e}")
            continue
        finally:
            (dest_dir / raw).unlink(missing_ok=True)
        rare = trim_all_ratings(low, high)
        (dest_dir / all_ratings_path(fid).name).write_text(json.dumps({"data": rare}, separators=(",", ":")),
                                                            encoding="utf-8")
        logging.info(f"Kept {len(rare)} rarely used Pokemon for {fid}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default=previous_month(), help="YYYY-MM, defaults to last month")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument("--all-ratings-only", action="store_true",
                        help="only (re)build the rarely used Pokemon files for the month already on disk")
    args = parser.parse_args()

    if args.all_ratings_only:
        month = read_manifest().get("month") or args.month
        with tempfile.TemporaryDirectory() as tmp:
            all_ratings(f"https://www.smogon.com/stats/{month}/", config.STATS_DIR, Path(tmp))
            for path in Path(tmp).iterdir():
                shutil.move(str(path), config.STATS_DIR / path.name)
        return

    if read_manifest().get("month") == args.month and not args.force:
        logging.info(f"Stats for {args.month} are already on disk.")
        # The RAG index lives only on this machine, so it can lag behind stats the monthly Action committed
        if args.rebuild_index:
            from metamatch.rag import build_index
            build_index.main()
        return

    month_url = f"https://www.smogon.com/stats/{args.month}/"
    if not month_published(month_url):
        # Not an error: Smogon is just late, and the next scheduled run will retry
        logging.warning(f"Smogon hasn't published {args.month} yet ({month_url}).")
        return

    # Download everything to a temp dir first so a failed run never leaves months mixed on disk
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        failed = []
        for index_url, remote, local in planned_downloads(month_url):
            if scrapers.download_stat_file(index_url, remote, local, dest_dir=tmp_dir):
                logging.info(f"Downloaded {local}")
            else:
                failed.append(local)
        if failed:
            logging.error(f"Aborting, {len(failed)} files failed: {', '.join(failed)}")
            sys.exit(1)
        all_ratings(month_url, tmp_dir, tmp_dir)
        for path in tmp_dir.iterdir():
            shutil.move(str(path), config.STATS_DIR / path.name)

    count = scrapers.refresh_derived()
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({
            "month": args.month,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "formats": {fid: fmt["stats"] for fid, fmt in config.FORMATS.items()},
            "pokemon": count,
        }, f, indent=2)
    logging.info(f"Stats updated to {args.month}.")

    # Month over month usage history for MetaFlash on the start screen
    from metamatch import meta_pulse, meta_trends
    history = meta_pulse.record_local_stats(meta_pulse.load_history(), args.month)
    meta_pulse.save_history(history)
    # Leads, sets and 1500+ usage for MetaFlash's trend sections (parsed straight into small histories)
    done, histories = meta_trends.fetch_month(args.month)
    meta_trends.save_all(histories)
    logging.info(f"MetaFlash trends for {args.month}: {done}")

    # Who plays rain, sun and sand (MetaFlash's weather watch and the chat's archetype answers). A failed download
    # keeps last month's file rather than failing the stats update
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build_archetypes
        build_archetypes.rebuild(args.month)
        logging.info(f"Archetype rosters rebuilt for {args.month}.")
    except Exception as e:
        logging.warning(f"Archetype rosters not rebuilt: {e}")

    if args.rebuild_index:
        from metamatch.rag import build_index
        build_index.main()


if __name__ == "__main__":
    main()
