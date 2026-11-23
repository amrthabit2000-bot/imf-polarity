"""Daily polarity of the interplanetary magnetic field (IMF) from hourly OMNI2 data.

Toward (T) and away (A) days are defined relative to the Parker spiral. With GSE components Bx, By,
the azimuth is phi = atan2(By, Bx) mod 360 deg. The nominal spiral points to 315 deg (toward the Sun)
and 135 deg (away from the Sun), so the boundary between the two polarities lies at 45 and 225 deg:

    halfplane rule (default):  T if 225 <= phi < 360 or 0 <= phi < 45,  A otherwise
    quadrant rule (OMNIWeb):   T if 270 <= phi < 360, A if 90 <= phi < 180, no label otherwise

A day is labelled from the azimuth of its daily mean (Bx, By) vector. It is kept only when it rests on
at least ``min_hours`` hourly values and when at least ``min_agreement`` of those hours have the same
polarity as the day (hourly polarities from the halfplane rule). The share of agreeing hours is returned
for every day so that users can apply a stricter threshold.
"""
import numpy as np
import pandas as pd

RULES = ("halfplane", "quadrant")
OMNI2_COLUMNS = {0: "year", 1: "doy", 2: "hour", 12: "Bx", 13: "By", 24: "V"}
OMNI2_FILL = {"Bx": 999.9, "By": 999.9, "V": 9999.0}


def azimuth(bx, by):
    """Azimuth of the (Bx, By) vector in GSE, in degrees from 0 to 360."""
    return np.degrees(np.arctan2(np.asarray(by, float), np.asarray(bx, float))) % 360.0


def classify(phi, rule="halfplane"):
    """Polarity label 'T', 'A' or '' (no label) for each azimuth phi (degrees)."""
    if rule not in RULES:
        raise ValueError(f"rule must be one of {RULES}")
    phi = np.asarray(phi, float)
    ok = np.isfinite(phi)
    if rule == "halfplane":
        lab = np.where((phi >= 225.0) | (phi < 45.0), "T", "A")
    else:
        # toward = [270, 360), away = [90, 180); the OMNIWeb table treats exact boundaries
        # (daily mean Bx or By exactly 0) inconsistently, so no convention reproduces all of them
        lab = np.where(phi >= 270.0, "T", np.where((phi >= 90.0) & (phi < 180.0), "A", ""))
    return np.where(ok, lab, "")


def read_omni2_hourly(paths):
    """Read OMNI2 hourly yearly files (omni2_YYYY.dat) into one DataFrame.

    Returns columns time, Bx, By (nT, GSE) and V (km/s); fill values are set to NaN.
    """
    if isinstance(paths, (str, bytes)) or hasattr(paths, "__fspath__"):
        paths = [paths]
    frames = []
    for p in paths:
        df = pd.read_csv(p, sep=r"\s+", header=None, usecols=list(OMNI2_COLUMNS))
        frames.append(df.rename(columns=OMNI2_COLUMNS))
    df = pd.concat(frames, ignore_index=True)
    for col, fill in OMNI2_FILL.items():
        df.loc[df[col] >= fill, col] = np.nan
    df["time"] = (
        pd.to_datetime(df.year.astype(int).astype(str), format="%Y")
        + pd.to_timedelta(df.doy - 1, unit="D")
        + pd.to_timedelta(df.hour, unit="h")
    )
    return df[["time", "Bx", "By", "V"]].sort_values("time").reset_index(drop=True)


def daily_polarity(hourly, rule="halfplane", min_hours=12, min_agreement=0.75):
    """Daily IMF polarity from hourly Bx, By (GSE).

    Parameters
    ----------
    hourly : DataFrame with columns time, Bx, By (one row per hour)
    rule : 'halfplane' (default) or 'quadrant'
    min_hours : minimum number of hours with both Bx and By
    min_agreement : minimum share of hours whose polarity equals that of the day (0 disables the test)

    Returns
    -------
    DataFrame indexed by date with Bx, By (daily means), phi, n_hours, frac_T_hours,
    polarity_raw (label of the daily mean vector), agreement and polarity ('' if the day fails a test).
    """
    h = hourly.dropna(subset=["Bx", "By"]).copy()
    h["date"] = h["time"].dt.normalize()
    h["hT"] = (classify(azimuth(h.Bx, h.By), "halfplane") == "T").astype(float)
    g = h.groupby("date")
    d = pd.DataFrame({"Bx": g.Bx.mean(), "By": g.By.mean(), "n_hours": g.hT.size(), "frac_T_hours": g.hT.mean()})
    # OMNI2 fields have 0.1 nT resolution; rounding removes floating-point noise so that a
    # daily mean of exactly zero falls on the boundary instead of on a random side of it.
    d[["Bx", "By"]] = d[["Bx", "By"]].round(9)
    d["phi"] = azimuth(d.Bx, d.By)
    d["polarity_raw"] = classify(d.phi, rule)
    d["agreement"] = np.where(
        d.polarity_raw == "T", d.frac_T_hours, np.where(d.polarity_raw == "A", 1.0 - d.frac_T_hours, np.nan)
    )
    keep = (d.polarity_raw != "") & (d.n_hours >= min_hours)
    if min_agreement > 0:
        keep &= d.agreement >= min_agreement
    d["polarity"] = np.where(keep, d.polarity_raw, "")
    d.index.name = "date"
    return d[["Bx", "By", "phi", "n_hours", "frac_T_hours", "polarity_raw", "agreement", "polarity"]]


def sort_by_polarity(values, polarity, freq="MS", min_days=3):
    """Mean of a daily series on toward and on away days, per period (default: calendar month).

    values, polarity : Series indexed by date; polarity holds 'T', 'A' or ''.
    Periods with fewer than ``min_days`` days of a polarity are left empty (NaN).
    Returns a DataFrame with columns T, A, n_T, n_A.
    """
    values, polarity = values.align(polarity, join="inner")
    out = {}
    for lab in ("T", "A"):
        x = values.where(polarity == lab)
        m = x.resample(freq).mean()
        n = x.resample(freq).count()
        out[lab] = m.where(n >= min_days)
        out["n_" + lab] = n
    return pd.DataFrame(out)[["T", "A", "n_T", "n_A"]]


def to_excel(days, path, settings=None, data=None, tables=None):
    """Write the results to an Excel file (needs openpyxl).

    Sheets: 'Polarity' (output of daily_polarity), 'Data' (``data``: every daily value, not split),
    one sheet per entry of ``tables`` (from sort_fields), and 'Settings' (``settings`` plus the data source).
    """
    pol = days.copy()
    pol.index = pol.index.date
    pol.index.name = "date"
    num = pol.select_dtypes("number").columns.drop("n_hours", errors="ignore")
    pol[num] = pol[num].round(4)
    pol[["polarity_raw", "polarity"]] = pol[["polarity_raw", "polarity"]].replace("", None)
    info = {"source": "NASA GSFC SPDF OMNI2 hourly data (https://omniweb.gsfc.nasa.gov)",
            "first day": str(pol.index.min()), "last day": str(pol.index.max()),
            "T days": int((days.polarity == "T").sum()), "A days": int((days.polarity == "A").sum()),
            "unlabelled days": int((days.polarity == "").sum())}
    info.update(settings or {})
    sheets = [("Polarity", pol)]
    if data is not None:
        d = data.copy()
        d.index = pd.Index(d.index.date, name="date")
        d.insert(0, "polarity", days.polarity.reindex(data.index).replace("", None).values)
        sheets.append(("Data", d))
    for name, t in (tables or {}).items():
        t = t.copy()
        if isinstance(t.index, pd.DatetimeIndex):
            t.index = pd.Index(t.index.date, name=t.index.name)
        sheets.append((name, t.round(4)))
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, frame in sheets:
            frame.to_excel(xw, sheet_name=name)
            ws = xw.sheets[name]
            ws.freeze_panes = "B2"
            for i in range(frame.shape[1] + 1):
                ws.column_dimensions[_excel_col(i)].width = 12 if i == 0 else 13
        pd.Series(info, name="value").rename_axis("item").to_frame().to_excel(xw, sheet_name="Settings")
        xw.sheets["Settings"].column_dimensions["A"].width = 30
        xw.sheets["Settings"].column_dimensions["B"].width = 70


def _excel_col(i):
    """Excel column letter for a 0-based column number."""
    name = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        name = chr(65 + r) + name
    return name


# OMNI2 quantities offered for toward/away sorting. Only quantities with a known physical link to the
# IMF polarity are listed: geomagnetic indices and GSM field/electric field, which respond to polarity
# through the Russell-McPherron effect (more activity on toward days in spring, on away days in autumn).
# name -> (0-based column, fill value, unit, always positive)
# Column numbers and fill values follow https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2.text
OMNI2_FIELDS = {
    "Dst": (40, 99999.0, "nT, Kyoto", False),
    "Kp_x10": (38, 99.0, "Kp*10 (3+ = 33, 4- = 37)", True),
    "ap": (49, 999.0, "nT", True),
    "AE": (41, 9999.0, "nT, Kyoto", True),
    "AL": (52, 99999.0, "nT, Kyoto", False),
    "AU": (53, 99999.0, "nT, Kyoto", False),
    "PC_N": (51, 999.9, "polar cap index (north)", False),
    "Bz_GSM": (16, 999.9, "nT", False),
    "E_field": (35, 999.99, "mV/m, -V*Bz(GSM)*1e-3", False),
}

# Meteorological seasons: the Russell-McPherron effect peaks in early April and early October, so the
# whole effect falls in MAM and SON, and JJA and DJF show almost none.
SEASONS = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}


def read_omni2_fields(paths, fields):
    """Hourly values of the named OMNI2 quantities (keys of OMNI2_FIELDS); fill values set to NaN."""
    unknown = [f for f in fields if f not in OMNI2_FIELDS]
    if unknown:
        raise ValueError(f"unknown OMNI2 quantity: {unknown}; choose from {list(OMNI2_FIELDS)}")
    if isinstance(paths, (str, bytes)) or hasattr(paths, "__fspath__"):
        paths = [paths]
    cols = {0: "year", 1: "doy", 2: "hour"}
    cols.update({OMNI2_FIELDS[f][0]: f for f in fields})
    df = pd.concat([pd.read_csv(p, sep=r"\s+", header=None, usecols=list(cols)).rename(columns=cols) for p in paths],
                   ignore_index=True)
    for f in fields:
        df.loc[df[f] >= OMNI2_FIELDS[f][1], f] = np.nan
    df["time"] = (pd.to_datetime(df.year.astype(int).astype(str), format="%Y")
                  + pd.to_timedelta(df.doy - 1, unit="D") + pd.to_timedelta(df.hour, unit="h"))
    return df[["time"] + list(fields)].sort_values("time").reset_index(drop=True)


def read_user_data(path, missing=None):
    """Read a user file (.csv, .txt or .xlsx) for toward/away sorting.

    Format: the first column holds the date or date-time (UT), every other column one quantity, with a
    header row giving the names. Empty cells, and cells equal to ``missing`` (e.g. -999), are missing values.
    Returns a DataFrame with a 'time' column and one numeric column per quantity.
    """
    ext = str(path).lower().rsplit(".", 1)[-1]
    if ext in ("xlsx", "xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, sep=None, engine="python")
    if df.shape[1] < 2:
        raise ValueError("The file needs a date column and at least one data column.")
    t = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    if t.isna().all():
        raise ValueError(f"The first column ({df.columns[0]}) could not be read as dates.")
    vals = df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    if missing is not None:
        vals = vals.mask(vals == missing)
    vals.columns = [str(c).strip() for c in vals.columns]
    out = pd.concat([t.rename("time"), vals], axis=1)
    out = out[out.time.notna()].sort_values("time").reset_index(drop=True)
    if vals.notna().sum().sum() == 0:
        raise ValueError("No numeric values were found in the data columns.")
    return out


def daily_means(hourly, min_hours=1):
    """Daily means of every column except 'time'; days with fewer than ``min_hours`` values are NaN."""
    x = hourly.set_index("time")
    m = x.resample("D").mean()
    n = x.resample("D").count()
    out = m.where(n >= min_hours)
    out.index.name = "date"
    return out


def _positive(name, values):
    if name in OMNI2_FIELDS:
        return OMNI2_FIELDS[name][3]
    v = values.dropna()
    return len(v) > 0 and bool((v >= 0).all())


def _pooled(v, pol, key, order):
    rows = {}
    for k in order:
        sel = key == k
        t, a = v[sel & (pol == "T")].dropna(), v[sel & (pol == "A")].dropna()
        rows[k] = {"T": t.mean() if len(t) else np.nan, "A": a.mean() if len(a) else np.nan,
                   "n_T": len(t), "n_A": len(a)}
    return pd.DataFrame.from_dict(rows, orient="index")


def _assemble(name, s, positive):
    t = pd.DataFrame({f"{name}_T": s["T"], f"{name}_A": s["A"], f"{name}_T-A": s["T"] - s["A"],
                      f"{name}_nT": s["n_T"], f"{name}_nA": s["n_A"]})
    if positive:
        tot = s["T"] + s["A"]
        t[f"{name}_ATA"] = ((s["T"] - s["A"]) / tot).where(tot > 0)
    return t


def sort_fields(daily, polarity, min_days=3):
    """Toward/away means of each daily column, in three tables.

    'Monthly': each calendar month of each year; a month is left empty for a quantity when it has fewer
    than ``min_days`` days of a polarity with data.
    'Calendar months': all T (A) days of January, February, ... pooled over every year.
    'Seasons': all T (A) days of DJF, MAM, JJA and SON pooled over every year.
    For each quantity: <name>_T, <name>_A, <name>_T-A, <name>_nT, <name>_nA, and <name>_ATA =
    (T - A)/(T + A) for quantities that are never negative.
    """
    daily, polarity = daily.align(polarity, join="inner", axis=0)
    month = pd.Series(daily.index.month, index=daily.index)
    season = month.map(SEASONS)
    out = {"Monthly": [], "Calendar months": [], "Seasons": []}
    for name in daily.columns:
        v = daily[name]
        pos = _positive(name, v)
        m = sort_by_polarity(v, polarity, freq="MS", min_days=min_days)
        out["Monthly"].append(_assemble(name, m, pos))
        c = _pooled(v, polarity, month, range(1, 13))
        out["Calendar months"].append(_assemble(name, c, pos))
        se = _pooled(v, polarity, season, ["DJF", "MAM", "JJA", "SON"])
        out["Seasons"].append(_assemble(name, se, pos))
    tables = {k: pd.concat(x, axis=1) for k, x in out.items()}
    tables["Monthly"].index.name = "month"
    tables["Calendar months"].index = pd.Index(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                                                "Oct", "Nov", "Dec"], name="calendar month")
    tables["Seasons"].index.name = "season"
    return tables


def asymmetry(t, a):
    """Toward-away asymmetry index (T - A) / (T + A) and log ratio ln(T / A)."""
    t = np.asarray(t, float)
    a = np.asarray(a, float)
    return (t - a) / (t + a), np.log(t / a)
