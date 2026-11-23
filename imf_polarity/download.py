"""Download OMNI2 hourly yearly files from NASA/GSFC SPDF."""
import time
from pathlib import Path

import requests

URL = "https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_{year}.dat"


def download_omni2(years, folder="omni2_hourly", refresh=False, tries=3):
    """Download omni2_YYYY.dat for each year into ``folder``; existing files are kept unless refresh=True.

    The two most recent years are still revised by the provider; use refresh=True to update them.
    Returns the list of local paths.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for year in years:
        path = folder / f"omni2_{year}.dat"
        if refresh or not path.exists() or path.stat().st_size == 0:
            for attempt in range(tries):
                try:
                    r = requests.get(URL.format(year=year), timeout=120)
                    r.raise_for_status()
                    tmp = path.with_suffix(".part")          # write to a temporary name first, so an
                    tmp.write_bytes(r.content)               # interrupted download never leaves a
                    tmp.replace(path)                        # truncated omni2_YYYY.dat behind
                    break
                except requests.RequestException:
                    if attempt == tries - 1:
                        raise
                    time.sleep(5)
        paths.append(path)
    return paths
