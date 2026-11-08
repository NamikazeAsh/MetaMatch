"""
Fills MetaFlash's histories with past months for every format: usage (data/json/usage_history.json) and
leads back to the start of the generation, plus the last 12 months of sets and 1500+ usage
(meta_trends.py). Only the small .txt tables are fetched, never the chaos files, and months a format
didn't exist yet are skipped. Months already on record are not downloaded again.

Usage:
  python scripts/backfill_usage_history.py                     # usage and leads since Nov 2022, sets for 12 months
  python scripts/backfill_usage_history.py --months 6 --set-months 3
"""
import argparse
import logging
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from metamatch import config, meta_pulse, meta_trends  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


FULL_HISTORY = 48   # Gen 9 ladders started in November 2022


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
    parser.add_argument("--months", type=int, default=FULL_HISTORY, help="months of usage and leads")
    parser.add_argument("--set-months", type=int, default=12, help="months of sets and 1500+ usage")
    args = parser.parse_args()

    last = meta_pulse.current_month()
    if not last:
        logging.error("No data/stats/manifest.json month; run scripts/update_meta.py first.")
        sys.exit(1)

    session = requests.Session()
    history = meta_pulse.load_history()
    # The month on disk comes from the local files, no download needed
    meta_pulse.record_local_stats(history, last)
    for month in months_back(last, args.months)[:-1]:
        for fid, fmt in config.FORMATS.items():
            if month in history.get(fid, {}):
                continue
            url = f"https://www.smogon.com/stats/{month}/{fmt['stats']}.txt"
            try:
                r = session.get(url, timeout=60)
            except requests.RequestException as e:
                logging.warning(f"{url}: {e}")
                continue
            if r.status_code != 200:
                continue
            rows = meta_pulse.parse_usage_text(r.text)
            if rows:
                meta_pulse.record_month(history, fid, month, rows)
                logging.info(f"{month} {fid}: {len(rows)} Pokemon")
        meta_pulse.save_history(history)   # after every month, so an interrupted run keeps what it fetched

    histories = None
    recent = set(months_back(last, args.set_months))
    for month in months_back(last, args.months):
        kinds = ("leads", "sets", "wide") if month in recent else ("leads",)
        done, histories = meta_trends.fetch_month(month, kinds, session=session, histories=histories)
        if any(done.values()):
            logging.info(f"{month} trends: {done}")
            meta_trends.save_all(histories)
    logging.info(f"Wrote {meta_pulse.HISTORY_PATH}")


if __name__ == "__main__":
    main()
