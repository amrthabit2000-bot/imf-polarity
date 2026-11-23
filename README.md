# imf-polarity

Daily toward/away polarity of the interplanetary magnetic field (IMF) from NASA OMNI2 hourly data, 1963 to the present, with a quality column for every day.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24443175.svg)](https://doi.org/10.5281/zenodo.24443175)

A day is **toward (T)** when the field points toward the Sun along the Parker spiral and **away (A)** when it points away from it. The package downloads the OMNI2 hourly files, labels each day, and sorts geomagnetic indices (Dst, Kp, ap, AE, AL, AU, PC(N)), Bz (GSM), the electric field, or the user's own daily data into T and A days by month, calendar month and season. It has a desktop window, a command line and a Python interface.

## Statement of need

Sorting geomagnetic activity by the polarity of the interplanetary magnetic field is a standard tool in solar-terrestrial physics: through the Russell–McPherron effect, toward days are more geoeffective in spring and away days in autumn. Studies use different rules to decide a day's polarity (half-plane or quadrant, with or without a check that the hours agree), often without stating them, and the T/A means depend on the rule. NASA's OMNIWeb daily polarity table gives one rule, without a quality measure or software.

imf-polarity gives researchers and students a documented, tested and reproducible way to (1) label every day since 1963 from OMNI2 hourly data with a stated rule and a per-day quality measure, (2) compare rules, and (3) sort geomagnetic indices or their own data into toward and away days by month, calendar month and season, with output in CSV and Excel. The rules were validated against the OMNIWeb table and against an independent ground-based polarity set (see Validation).

## Method

1. **Hourly data.** Bx and By (GSE, nT) from OMNI2 hourly files (King and Papitashvili, 2005). Fill values (999.9) are removed.
2. **Daily vector.** Bx and By are averaged over the day and the azimuth φ = atan2(By, Bx) is taken in 0–360°.
3. **Polarity rule.**
   - `halfplane` (default): T if φ ≥ 225° or φ < 45°, A otherwise. The boundary line 45°–225° is perpendicular to the mean Parker spiral (135°/315°), so every day gets the polarity whose spiral direction is closest.
   - `quadrant`: T if 270° ≤ φ < 360°, A if 90° ≤ φ < 180°, no label in the other two quadrants. This is the rule used for the OMNIWeb daily polarity table and is included for compatibility with it.
4. **Quality tests** (a day that fails is left unlabelled):
   - `min_hours` (default 12): at least 12 hours with both Bx and By;
   - `min_agreement` (default 0.75): at least 75 % of the hours must have the same half-plane polarity as the daily vector. This rejects days that contain a sector boundary or a mixed field. Set it to 0 to disable the test.

### Output columns

| column | meaning |
|---|---|
| `date` | day (UT) |
| `Bx`, `By` | daily mean field, nT, GSE |
| `phi` | azimuth of the daily mean vector, degrees |
| `n_hours` | hours with both Bx and By |
| `frac_T_hours` | share of hours with toward half-plane polarity |
| `polarity_raw` | label of the daily vector before the quality tests |
| `agreement` | share of hours that agree with `polarity_raw` |
| `polarity` | final label: `T`, `A`, or empty |

`agreement` can be used as a quality weight, or to choose a stricter threshold than the default.

## Installation

Python 3.9 or later. Tested with Python 3.11, numpy 2.4.6, pandas 2.3.3, requests 2.34.2, openpyxl 3.1.5 and matplotlib 3.11.2; the automated tests also run with the oldest supported versions (numpy 1.23, pandas 1.5).

Install from GitHub, with the plotting extra:

```
python -m pip install "imf-polarity[plot] @ git+https://github.com/amrthabit2000-bot/imf-polarity@v1.0.2"
```

or from a downloaded copy of the repository (or the Zenodo archive):

```
python -m pip install .[plot]
```

This installs the commands `imf-polarity` (command line) and `imf-polarity-gui` (desktop window). Without installing, `pip install -r requirements.txt` and `python -m imf_polarity` also work from the repository folder. An Arabic user guide is in `docs/imf-polarity_User_Guide_AR.docx`.

## Usage

### Desktop window

Double-click `Start_IMF_Polarity.bat` (Windows), or run:

```
python -m imf_polarity.gui
```

The window has four tabs:

1. **Polarity**: first and last year; a setting list (default, strict 90 %, OMNIWeb table, or custom); rule; minimum hours; minimum hour agreement.
2. **Quantities**: the OMNI2 quantities to sort into T and A; your own data file with its missing-value code, and a **Check file** button that reports the columns found, the dates, values per day, missing values, and whether the asymmetry index will be computed; the minimum number of days of each polarity in a month.
3. **Output**: data and output folders; output file name; CSV and/or Excel; refresh of the downloaded data.
4. **Results**: the number of T, A and unlabelled days; a table of T − A by season for each quantity; a plot of T − A by calendar month and by season, with 95 % intervals from the scatter between years and the two equinoxes marked, and **Save plot** (PNG, PDF or SVG, 300 dpi).

Below the tabs: Run, Cancel (stops after the current step), Open output folder, Open Excel file, About the method, a progress bar and a log. Hovering over an option shows a short help text. The settings are saved in `.imf_polarity_gui.json` in the user's home folder and restored at the next start. The plot needs matplotlib; without it the window works without the plot.

### Command line

Daily polarity only (the OMNI2 files are downloaded into `omni2_hourly/`):

```
python -m imf_polarity --start 1963 --end 2026 --out daily_polarity.csv --excel
python -m imf_polarity --start 1963 --end 2026 --min-agreement 0.9 --out strict.csv
python -m imf_polarity --start 1963 --end 2026 --rule quadrant --min-agreement 0 --out omniweb_like.csv
```

`--excel` also writes an Excel file with the same name; an output name ending in `.xlsx` writes only the Excel file. Files already present are not downloaded again; add `--refresh` to download the latest version of every file (the current year and recently revised years change).

Sorting quantities into T and A:

```
python -m imf_polarity --list-fields
python -m imf_polarity --start 1963 --end 2026 --out results.csv --excel --fields Dst,Kp_x10,AE
python -m imf_polarity --start 1963 --end 2026 --out results.csv --excel --user-data my_data.csv --missing -999
```

### Python

```python
from imf_polarity import (download_omni2, read_omni2_hourly, daily_polarity, read_omni2_fields,
                          read_user_data, daily_means, sort_fields, to_excel)

paths = download_omni2(range(1963, 2027), "omni2_hourly")
days = daily_polarity(read_omni2_hourly(paths))
daily = daily_means(read_omni2_fields(paths, ["Kp_x10", "Dst"]))
tables = sort_fields(daily, days.polarity, min_days=3)      # Monthly, Calendar months, Seasons
to_excel(days, "results.xlsx", {"rule": "halfplane"}, daily, tables)

import matplotlib.pyplot as plt                              # optional plot
from imf_polarity import plot_ta
fig = plt.figure(figsize=(7.2, 3.2))
plot_ta(fig, tables, "Kp_x10", "1963-2026")
fig.savefig("kp_ta.png", dpi=300)
```

In the plot, bars are the pooled T − A values of the tables; error bars are 95 % intervals (Student t) of the year-to-year scatter of the monthly T − A values (seasons: mean of their months per year, December counted with the following DJF).

Examples:
- `examples/seasonal_kp_dst.py`: T − A of Kp and Dst by calendar month and season (Russell–McPherron effect).
- `examples/compare_with_omniweb_table.py`: comparison of the quadrant rule with the OMNIWeb polarity table.

## Sorting quantities into T and A

**Quantities.** The OMNI2 list holds only quantities with a known physical link to the IMF polarity: `Dst`, `Kp_x10` (Kp × 10, as stored in OMNI2), `ap`, `AE`, `AL`, `AU`, `PC_N`, `Bz_GSM` and `E_field`. They respond to polarity through the Russell–McPherron effect: the GSM projection makes toward days more geoeffective in spring and away days in autumn. `Bz_GSM` is the projection itself, so its T − A difference is geometric. Bx and By are not offered, because the polarity is defined from them and their T − A difference follows from the definition. Solar wind plasma and solar indices are not offered either: polarity does not drive them, and any T − A difference reflects which solar sources the Earth samples.

**Your own data.** A `.csv` or `.xlsx` file: the first column holds the date or date-time (UT), every other column one quantity, with names in the first row. Empty cells, and cells equal to the missing-value code, are ignored. Values within a UT day are averaged. A sorted difference does not show a physical effect by itself. The Earth's heliographic latitude changes over the year, so the dominant polarity it sees changes with season and with the solar cycle (Rosenberg and Coleman, 1969); a quantity that follows the solar cycle can therefore show a seasonal T − A pattern with no polarity effect. With the daily sunspot number for 1992–2026, for example, T − A is −12.0 in MAM and +2.7 in SON.

**Output tables.**
- `Monthly`: each month of each year. A month is left empty for a quantity when it has fewer than `--min-days` days of a polarity (default 3).
- `Calendar months`: all T (A) days of each calendar month pooled over all years. This is the table to use for the seasonal effect.
- `Seasons`: all T (A) days of DJF, MAM, JJA and SON pooled over all years. Meteorological seasons are used because the Russell–McPherron effect peaks in early April and early October: over 1963–2026, T − A of Kp × 10 is +6.97 in MAM and −7.80 in SON, against −0.67 in JJA and +0.07 in DJF.

For each quantity the tables give `<name>_T`, `<name>_A`, `<name>_T-A`, the numbers of days `<name>_nT` and `<name>_nA`, and `<name>_ATA` = (T − A)/(T + A) for quantities that are never negative (and T + A > 0). Annual or whole-record means are not offered: the spring and autumn halves cancel (over 1963–2026, whole-record T − A of Dst is 0.29 nT with p = 0.61, while its spring-minus-autumn difference is −30.8 nT with p = 0.002 in a circular-shift test).

**Minimum days per month.** Tested on Kp and Dst, 1963–2026. A month has a median of 11 T and 10 A labelled days, and 10 % of months have fewer than 3 days of one polarity. Labelled sectors last 3 days (median), so a 3-day mean is close to a single sector passage, and its scatter is large (standard deviation of a 3-day mean about the monthly mean: 6.0 for Kp × 10 and 8.8 nT for Dst, against 2.2 and 3.3 nT for 10 days). Single monthly values with few days should therefore not be read one by one. For the seasonal amplitude built from monthly values, the ratio of amplitude to standard error is largest at 3 to 5 days (Kp × 10: 16.6, 20.4, 18.3, 17.8 and 12.7 for 1, 3, 5, 7 and 10 days), and the amplitude itself does not change with the threshold. The default of 3 days is kept; the calendar-month and seasonal tables pool all days and do not use it.

**Days are not independent.** Sectors persist for several days and recur every 27 days, so simple standard errors of T − A are too small. Use a test that keeps the autocorrelation, such as shifting the polarity series by whole years.

## Validation

**Tests.** `python -m pytest` runs 16 tests with known answers: rule boundaries, spiral directions, the agreement threshold (18 of 24 hours passes, 17 of 24 fails), the hour count, a day off the spiral, missing hours, recovery of a planted toward–away difference, an Excel write/read round trip, a full run of the desktop window's run function on a synthetic data file, the T/A tables for planted Dst and Kp values (including a fill value and the minimum-days rule), a user data file with a missing-value code, the window's file check, and the 95 % intervals of the plot.

**OMNIWeb table.** With `rule="quadrant"` the package gives the same code as the OMNIWeb daily polarity table on 20,345 of 20,356 days (1963-11-27 to 2026-10-29). Six of the 11 differences are days whose mean Bx or By is exactly zero, so the vector lies on a quadrant boundary; the table does not treat such days in a consistent way. The other five are in 2021 and 2023.

**Independent ground-based polarities.** Daily labels were compared with the C7 polarity set (Thule, Vostok and Mirny geomagnetic stations) of Vokhmyanin and Zolotova (2022) for 1963-11-27 to 2026-10-14 (file `validation/agreement_with_C7.csv`):

| rule | filter | labelled days | days with C7 | agreement with C7 |
|---|---|---|---|---|
| half-plane | all days | 20,341 | 14,184 | 0.9025 |
| half-plane | ≥12 h | 18,635 | 12,880 | 0.9061 |
| **half-plane** | **≥12 h, ≥75 % (default)** | **15,673** | **10,814** | **0.9486** |
| half-plane | ≥12 h, ≥90 % | 11,980 | 8,278 | 0.9677 |
| quadrant | all R/B days | 17,605 | 12,277 | 0.9379 |
| quadrant | ≥12 h (as OMNIWeb table) | 16,232 | 11,232 | 0.9402 |
| quadrant | ≥12 h, ≥75 % | 14,748 | 10,191 | 0.9591 |

Standard errors are about 0.002. The hour-agreement test gives the largest gain. C7 is itself an inferred polarity with its own errors, so these values are agreement rates, not accuracies. The quadrant rule keeps only days near the spiral directions, and part of its higher agreement may come from that selection. It removes 346 days that the half-plane rule labels with at least 90 % hour agreement; those days agree with C7 on 0.834 of the 223 days where C7 exists, which is less than other well-defined days.

**Tested and not adopted.** A spiral angle that depends on the daily solar wind speed, ψ = atan(Ωr/V), and an hour-by-hour majority vote were also tested. Neither changed the agreement with C7 by more than the standard error, so the fixed 45° boundary was kept.

## Choosing a setting

- General use: the default (`halfplane`, 12 h, 75 %).
- Fewer misclassified days at the cost of fewer days: raise `--min-agreement` to 0.9.
- To match the OMNIWeb table: `--rule quadrant --min-agreement 0`.

Report the setting you use; results that depend on the polarity of a small number of days should be checked with a second setting.

## Other OMNI2 columns

The yearly files hold 55 columns per hour; the full list with fill values is in NASA's format description, https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2.text. Columns outside the list above can be sorted as your own data file, with the caution given there.

## Data and citation

OMNI2 data: NASA Goddard Space Flight Center, Space Physics Data Facility, OMNIWeb (https://omniweb.gsfc.nasa.gov). Please acknowledge OMNIWeb and cite King and Papitashvili (2005) when you use the data.

If you use this package, please cite it as given in `CITATION.cff`.

## References

- King, J. H., and Papitashvili, N. E. (2005). Solar wind spatial scales in and comparisons of hourly Wind and ACE plasma and magnetic field data. *J. Geophys. Res.*, 110, A02104. https://doi.org/10.1029/2004JA010649
- Rosenberg, R. L., and Coleman, P. J. (1969). Heliographic latitude dependence of the dominant polarity of the interplanetary magnetic field. *J. Geophys. Res.*, 74, 5611. https://doi.org/10.1029/JA074i024p05611
- Russell, C. T., and McPherron, R. L. (1973). Semiannual variation of geomagnetic activity. *J. Geophys. Res.*, 78, 92. https://doi.org/10.1029/JA078i001p00092
- Vokhmyanin, M. V., and Zolotova, N. V. (2022). Long-term north–south asymmetry of the heliospheric current sheet. *Astrophys. J.*, 928, 56. https://doi.org/10.3847/1538-4357/ac5630

## Community guidelines

- **Report a problem or ask a question:** open an issue at https://github.com/amrthabit2000-bot/imf-polarity/issues, with the version, the command or code, and the full error message.
- **Contribute:** see [CONTRIBUTING.md](CONTRIBUTING.md). Every new option needs a known-answer test, and any change to a computed result must be stated in [CHANGELOG.md](CHANGELOG.md).
- **Conduct:** everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

MIT (see `LICENSE`).
