"""
Fills data/json/usage_history.json with past months of Smogon usage for every format, so the
Meta Pulse can show month over month moves and sparklines. Only the small usage .txt tables are
fetched (about 100 KB each), never the chaos files. Months a format didn't exist yet are skipped.

Usage:
  python scripts/backfill_usage_history.py              # the 6 months up to the one on disk
  python scripts/backfill_usage_history.py --months 12
"""
import argparse
import logging
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from metamatch import config, meta_pulse  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def months_back(last, count):
    """['2026-05', ..., '2026-10'] for last='2026-10', count=6."""
    year, mon = map(int, last.split("-"))
    out = []
    for _ in range(count):
        out.append(f"{year:04d}-{mon:02d}")
        mon -= 1
        if mon == 0:
            year, mon = year - 1, 12
    return out[::-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=meta_pulse.SPARK_MONTHS)
    args = parser.parse_args()

    last = meta_pulse.current_month()
    if not last:
        logging.error("No data/stats/manifest.json month; run scripts/update_meta.py first.")
        sys.exit(1)

    history = meta_pulse.load_history()
    # The month on disk comes from the local files, no download needed
    meta_pulse.record_local_stats(history, last)
    for month in months_back(last, args.months)[:-1]:
        for fid, fmt in config.FORMATS.items():
            if month in history.get(fid, {}):
                continue
            url = f"https://www.smogon.com/stats/{month}/{fmt['stats']}.txt"
            try:
                r = requests.get(url, timeout=60)
            except requests.RequestException as e:
                logging.warning(f"{url}: {e}")
                continue
            if r.status_code != 200:
                logging.info(f"{month} {fid}: not published ({r.status_code}), skipping")
                continue
            rows = meta_pulse.parse_usage_text(r.text)
            if rows:
                meta_pulse.record_month(history, fid, month, rows)
                logging.info(f"{month} {fid}: {len(rows)} Pokemon")
    meta_pulse.save_history(history)
    logging.info(f"Wrote {meta_pulse.HISTORY_PATH}")


if __name__ == "__main__":
    main()
