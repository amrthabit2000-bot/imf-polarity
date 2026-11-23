"""Plot of the toward-minus-away difference by calendar month and by season (needs matplotlib)."""
import numpy as np
import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SEASONS = ["DJF", "MAM", "JJA", "SON"]
LABELS = {"Dst": ("Dst", "nT"), "Kp_x10": ("Kp \u00d7 10", ""), "ap": ("ap", "nT"), "AE": ("AE", "nT"),
          "AL": ("AL", "nT"), "AU": ("AU", "nT"), "PC_N": ("PC(N)", ""), "Bz_GSM": ("Bz (GSM)", "nT"),
          "E_field": ("E = \u2212V Bz", "mV/m")}
COLOR_T, COLOR_A = "#C8553D", "#2E6F9E"          # T higher / A higher (blue-orange pair, colour-blind safe)
# two-sided 95 % Student t quantiles for 1-30 degrees of freedom; 1.96 above
_T95 = [12.71, 4.30, 3.18, 2.78, 2.57, 2.45, 2.36, 2.31, 2.26, 2.23, 2.20, 2.18, 2.16, 2.14, 2.13, 2.12, 2.11,
        2.10, 2.09, 2.09, 2.08, 2.07, 2.07, 2.06, 2.06, 2.06, 2.05, 2.05, 2.05, 2.04]


def _half_width(values):
    v = pd.Series(values).dropna()
    k = len(v)
    if k < 2:
        return np.nan
    t = _T95[k - 2] if k - 1 <= 30 else 1.96
    return t * v.std(ddof=1) / np.sqrt(k)


def yearly_intervals(monthly, name):
    """95 % half-widths of T - A for each calendar month and season, from the scatter between years.

    ``monthly`` is the 'Monthly' table of sort_fields. Each year gives one T - A value per calendar month
    (and one per season, the mean of its months; December counts with the following year's DJF).
    """
    d = monthly[f"{name}_T-A"].dropna()
    idx = pd.DatetimeIndex(d.index)
    cm = [_half_width(d[idx.month == m]) for m in range(1, 13)]
    season = pd.Series(idx.month, index=d.index).map({12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
                                                      6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"})
    year = pd.Series(idx.year + (idx.month == 12), index=d.index)
    per_year = d.groupby([season.values, year.values]).mean()
    se = [_half_width(per_year.loc[s]) if s in per_year.index.get_level_values(0) else np.nan for s in SEASONS]
    return np.array(cm), np.array(se)


def plot_ta(fig, tables, name, period_label=""):
    """Draw T - A of ``name`` by calendar month and by season into the matplotlib Figure ``fig``."""
    label, unit = LABELS.get(name, (name, ""))
    cm = tables["Calendar months"][f"{name}_T-A"].values.astype(float)
    se = tables["Seasons"][f"{name}_T-A"].values.astype(float)
    nT = int(tables["Seasons"][f"{name}_nT"].sum())
    nA = int(tables["Seasons"][f"{name}_nA"].sum())
    e_cm, e_se = yearly_intervals(tables["Monthly"], name)
    nyears = pd.DatetimeIndex(tables["Monthly"][f"{name}_T-A"].dropna().index).year.nunique()

    fig.clear()
    small, base = 7.5, 8.5
    gs = fig.add_gridspec(1, 2, width_ratios=[3.2, 1.2], wspace=0.06, left=0.09, right=0.99, top=0.74, bottom=0.2)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharey=ax1)
    for ax, x, y, e in ((ax1, np.arange(12), cm, e_cm), (ax2, np.arange(4), se, e_se)):
        colors = [COLOR_T if v > 0 else COLOR_A for v in y]
        ax.bar(x, y, width=0.68, color=colors, zorder=2)
        ax.errorbar(x, y, yerr=e, fmt="none", ecolor="#333333", elinewidth=0.9, capsize=2.5, zorder=3)
        ax.axhline(0, color="black", lw=0.8, zorder=1)
        ax.grid(axis="y", lw=0.4, color="#dddddd", zorder=0)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(labelsize=small)
        ax.margins(x=0.03)
    ax1.set_xticks(range(12), MONTHS)
    ax2.set_xticks(range(4), SEASONS)
    ax2.tick_params(labelleft=False)
    # equinoxes (about 20 March and 22 September): positions within the month bars
    for xq, txt in ((2 + 19.5 / 31 - 0.5, "March\nequinox"), (8 + 21.5 / 30 - 0.5, "September\nequinox")):
        ax1.axvline(xq, color="#888888", lw=0.8, ls=":", zorder=1)
        ax1.text(xq, 1.0, txt, transform=ax1.get_xaxis_transform(), ha="center", va="bottom",
                 fontsize=small, color="#666666")
    ax1.set_ylabel(f"T \u2212 A of {label}" + (f" ({unit})" if unit else ""), fontsize=base)
    ax1.set_title("By calendar month", fontsize=base, loc="left", pad=22)
    ax2.set_title("By season", fontsize=base, loc="left", pad=22)
    from matplotlib.patches import Patch
    ax2.legend(handles=[Patch(color=COLOR_T, label="T higher"), Patch(color=COLOR_A, label="A higher")],
               fontsize=small, frameon=False, loc="best")
    fig.suptitle(f"{label}: toward (T) minus away (A) days" + (f", {period_label}" if period_label else ""),
                 fontsize=base + 1, x=0.09, y=0.985, ha="left", va="top")
    fig.text(0.09, 0.02, f"All years pooled: {nT} T days, {nA} A days. Error bars: 95 % interval from the "
                         f"scatter between {nyears} years.", fontsize=small, color="#555555", ha="left")
    return fig
