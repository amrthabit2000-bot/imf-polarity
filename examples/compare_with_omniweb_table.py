"""Check: quadrant rule of this package against the OMNIWeb daily polarity table.

The table (https://omniweb.gsfc.nasa.gov/html/polarity/polarity_tab.html) gives one code per
day: R (toward), B (away), Y (mixed) or W (no data). This script rebuilds the codes from the
OMNI2 hourly files with rule='quadrant' and reports the share of identical days.

Run from the repository folder:  python examples/compare_with_omniweb_table.py
"""
import datetime as dt
import re

import pandas as pd
import requests

from imf_polarity import daily_polarity, download_omni2, read_omni2_hourly

URL = "https://omniweb.gsfc.nasa.gov/html/polarity/polarity_tab.html"

text = requests.get(URL, timeout=120).text
dates, codes = [], []
for line in text.splitlines():
    if re.match(r"^\s*\d{4}\s", line):
        parts = line.split()
        first = pd.Timestamp(int(parts[0]), 1, 1) + pd.Timedelta(days=int(parts[1]) - 1)
        for i, c in enumerate(parts[3:]):          # parts[2] is the Bartels rotation number
            dates.append(first + pd.Timedelta(days=i))
            codes.append(c)
table = pd.Series(codes, index=pd.DatetimeIndex(dates))
table = table[~table.index.duplicated()]

paths = download_omni2(range(1963, dt.date.today().year + 1), "omni2_hourly")
days = daily_polarity(read_omni2_hourly(paths), rule="quadrant", min_hours=1, min_agreement=0)
ours = days.polarity_raw.map({"T": "R", "A": "B"}).fillna("Y")

both = pd.concat([ours.rename("package"), table.rename("omniweb"), days.Bx, days.By], axis=1, join="inner")
both = both[both.omniweb != "W"]
same = both.package == both.omniweb
edge = (both.Bx == 0) | (both.By == 0)             # daily mean exactly on a quadrant boundary
print(f"days compared: {len(both)}, identical: {same.sum()} ({same.mean():.4%})")
print(f"days off the boundaries: {(~edge).sum()}, identical: {same[~edge].sum()} ({same[~edge].mean():.4%})")
print(both[~same].to_string())
