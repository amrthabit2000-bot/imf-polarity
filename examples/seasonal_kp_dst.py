"""Example: seasonal toward/away difference of geomagnetic activity (Russell-McPherron effect).

Downloads the OMNI2 hourly files, labels each day toward (T) or away (A), and prints the T - A
difference of Kp*10 and Dst for each calendar month and each season. Toward days are more active
in spring (MAM) and away days in autumn (SON); the two halves cancel in annual means, which is why
the tool gives monthly, calendar-month and seasonal tables only.

Run from the repository folder:  python examples/seasonal_kp_dst.py
"""
import datetime as dt

from imf_polarity import daily_means, daily_polarity, download_omni2, read_omni2_fields, read_omni2_hourly, sort_fields

paths = download_omni2(range(1963, dt.date.today().year + 1), "omni2_hourly")
days = daily_polarity(read_omni2_hourly(paths))
daily = daily_means(read_omni2_fields(paths, ["Kp_x10", "Dst"]))
tables = sort_fields(daily, days.polarity)

cols = ["Kp_x10_T-A", "Dst_T-A", "Kp_x10_nT", "Kp_x10_nA"]
print(tables["Calendar months"][cols].round(2).to_string())
print()
print(tables["Seasons"][cols].round(2).to_string())
