"""Complete run used by the command line and by the desktop window."""
import datetime as dt
import os

import pandas as pd

from .core import (daily_means, daily_polarity, read_omni2_fields, read_omni2_hourly, read_user_data, sort_fields,
                   to_excel)
from .download import download_omni2

class Cancelled(Exception):
    """Raised when the user stops a run."""


TABLE_FILES = {"Monthly": "monthly", "Calendar months": "calendar_months", "Seasons": "seasons"}


def run_job(p, log=print, progress=lambda done, total: None, should_stop=lambda: False):
    """Download, classify, sort the chosen quantities by polarity, and write the output files.

    ``p`` is a dict with keys start, end, data, refresh, rule, min_hours, min_agreement (percent),
    out_dir, name, csv, excel, and optionally fields (list of OMNI2_FIELDS names), user_file (path of a
    user data file), missing (missing-value code in that file) and min_days (default 3).
    ``should_stop`` is called between steps; when it returns True the run stops with Cancelled.
    Returns a dict with the output paths, the day counts and the tables.
    """
    fields = list(p.get("fields") or [])
    user_file = p.get("user_file") or None
    min_days = int(p.get("min_days", 3))
    if p["start"] > p["end"]:
        raise ValueError("The first year is after the last year.")
    if not (p["csv"] or p["excel"]):
        raise ValueError("Choose at least one output format (CSV or Excel).")
    if min_days < 1:
        raise ValueError("Minimum days per polarity must be at least 1.")
    if p["excel"]:
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            raise ValueError("Excel output needs the openpyxl package:  python -m pip install openpyxl")
    user = None
    if user_file:
        log(f"Reading {os.path.basename(user_file)} ...")
        user = daily_means(read_user_data(user_file, p.get("missing")))
        clash = [c for c in user.columns if c in fields or c in ("polarity",)]
        user = user.rename(columns={c: "user_" + c for c in clash})
        log(f"  {user.shape[1]} quantities, {user.index.min().date()} to {user.index.max().date()}")
    years = list(range(p["start"], p["end"] + 1))
    total = len(years) + 3
    paths = []
    for i, year in enumerate(years, 1):
        if should_stop():
            raise Cancelled("Run stopped by the user.")
        log(f"OMNI2 {year} ...")
        paths += download_omni2([year], p["data"], refresh=p["refresh"])
        progress(i, total)
    if should_stop():
        raise Cancelled("Run stopped by the user.")
    log("Reading hourly data and classifying days ...")
    days = daily_polarity(read_omni2_hourly(paths), p["rule"], p["min_hours"], p["min_agreement"] / 100.0)
    progress(len(years) + 1, total)
    data, tables = None, None
    parts = []
    if fields:
        parts.append(daily_means(read_omni2_fields(paths, fields)).reindex(days.index))
    if user is not None:
        overlap = user.index.intersection(days.index[days.polarity != ""])
        if len(overlap) == 0:
            raise ValueError("The user data do not overlap the labelled days of the chosen years.")
        log(f"  {len(overlap)} labelled days overlap the user data")
        parts.append(user)
    if should_stop():
        raise Cancelled("Run stopped by the user.")
    if parts:
        data = pd.concat(parts, axis=1).sort_index()
        data.index.name = "date"
        log("Sorting by polarity (monthly, calendar months, seasons) ...")
        tables = sort_fields(data, days.polarity, min_days=min_days)
    progress(len(years) + 2, total)
    os.makedirs(p["out_dir"], exist_ok=True)
    base = os.path.join(p["out_dir"], p["name"])
    outputs = []
    if p["csv"]:
        days.to_csv(base + ".csv", float_format="%.4f")
        outputs.append(base + ".csv")
        if data is not None:
            data.to_csv(base + "_data.csv", float_format="%.4f")
            outputs.append(base + "_data.csv")
            for k, t in tables.items():
                t.to_csv(f"{base}_{TABLE_FILES[k]}.csv", float_format="%.4f")
                outputs.append(f"{base}_{TABLE_FILES[k]}.csv")
    if p["excel"]:
        settings = {"rule": p["rule"], "min_hours": p["min_hours"], "min_agreement": p["min_agreement"] / 100.0,
                    "years requested": f"{p['start']}-{p['end']}", "created": dt.date.today().isoformat()}
        if data is not None:
            settings.update({
                "OMNI2 quantities": ", ".join(fields) or "-",
                "user data file": os.path.basename(user_file) if user_file else "-",
                "daily value": "mean of the values within each UT day",
                "Monthly": f"each month of each year; empty when fewer than {min_days} days of a polarity",
                "Calendar months": "all T (A) days of each calendar month, pooled over all years",
                "Seasons": "DJF, MAM, JJA, SON, all T (A) days pooled over all years",
                "ATA": "(T - A)/(T + A), only for quantities that are always positive"})
        to_excel(days, base + ".xlsx", settings, data, tables)
        outputs.append(base + ".xlsx")
    progress(total, total)
    n = days.polarity.value_counts()
    return {"outputs": outputs, "days": len(days), "T": int(n.get("T", 0)), "A": int(n.get("A", 0)),
            "unlabelled": int(n.get("", 0)),
            "first": str(days.index.min().date()) if len(days) else "-",
            "last": str(days.index.max().date()) if len(days) else "-",
            "tables": tables}
