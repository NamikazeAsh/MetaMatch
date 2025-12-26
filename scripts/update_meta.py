import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import requests
import logging

# Setup Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.metamatch import scrapers
from src.metamatch import config

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_target_month_url():
    """
    Returns the URL for the previous month's stats (e.g., if today is Nov 2023, returns .../2023-10/)
    """
    today = datetime.today()
    # Go to first day of current month
    first_current = today.replace(day=1)
    # Go back one day to get previous month
    last_prev = first_current - timedelta(days=1)
    
    url = f"https://www.smogon.com/stats/{last_prev.year:04d}-{last_prev.month:02d}/"
    logging.info(f"Targeting stats for: {last_prev.strftime('%B %Y')} at {url}")
    return url

def check_url_exists(url):
    try:
        r = requests.head(url)
        return r.status_code == 200
    except:
        return False

def main():
    target_url = get_target_month_url()
    
    # 1. Check if Smogon has uploaded the stats yet
    if not check_url_exists(target_url):
        logging.warning(f"Stats not found at {target_url}. Smogon might be late.")
        # Optional: We could exit with error to fail a CI job, or exit 0 to just 'skip'
        sys.exit(0)

    logging.info("Stats URL found! Starting download pipeline...")

    # 2. Download the Chaos Data (JSON) & Usage Text
    # We target Gen 9 OU (1695 or 1825 rating is standard for 'high ladder' logic)
    # Using 1825 for higher precision validation
    file_map = {
        "gen9ou-1825.json": "chaos.json",
        "gen9ou-1825.txt": "usage.txt"
    }

    success_count = 0
    for remote_file, local_alias in file_map.items():
        # scrapers.download_stat_file saves to config.STATS_DIR
        # We might need to rename it after download if we want a fixed name like 'chaos.json' 
        # or just keep the dated name. For now, let's stick to the raw download.
        local_path = scrapers.download_stat_file(target_url, remote_file)
        
        if local_path:
            success_count += 1
            logging.info(f"Downloaded: {remote_file}")
        else:
            logging.error(f"Failed to download: {remote_file}")

    if success_count > 0:
        logging.info("Update complete.")
        # Here we could trigger a rebuild of other indices if necessary
    else:
        logging.error("No files were downloaded.")
        sys.exit(1)

if __name__ == "__main__":
    main()
