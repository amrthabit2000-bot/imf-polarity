"""Command line: python -m imf_polarity --start 1963 --end 2026 --out daily_polarity.csv"""
import argparse
import datetime as dt
import os

from .core import OMNI2_FIELDS
from .workflow import run_job


def main(argv=None):
    p = argparse.ArgumentParser(prog="imf_polarity", description="Daily IMF toward/away polarity from OMNI2 hourly data")
    p.add_argument("--start", type=int, default=1963, help="first year (default 1963)")
    p.add_argument("--end", type=int, default=dt.date.today().year, help="last year (default: current year)")
    p.add_argument("--data", default="omni2_hourly", help="folder for the OMNI2 files")
    p.add_argument("--out", default="daily_polarity.csv", help="output file, .csv or .xlsx (default daily_polarity.csv)")
    p.add_argument("--rule", choices=["halfplane", "quadrant"], default="halfplane")
    p.add_argument("--min-hours", type=int, default=12)
    p.add_argument("--min-agreement", type=float, default=0.75)
    p.add_argument("--refresh", action="store_true", help="download every file again")
    p.add_argument("--excel", action="store_true", help="also write an Excel file with the same name (.xlsx)")
    p.add_argument("--fields", default="", help="OMNI2 quantities to sort by polarity, comma separated (e.g. Dst,Kp_x10,AE)")
    p.add_argument("--user-data", default="", help="your own data file (.csv or .xlsx): first column date, other columns values")
    p.add_argument("--missing", type=float, default=None, help="missing-value code in the user data file (e.g. -999)")
    p.add_argument("--min-days", type=int, default=3, help="minimum days of a polarity in a month (default 3)")
    p.add_argument("--list-fields", action="store_true", help="list the OMNI2 quantities and exit")
    a = p.parse_args(argv)
    if a.list_fields:
        for name, (col, fill, unit, _) in OMNI2_FIELDS.items():
            print(f"{name:10s} column {col:2d}  {unit}")
        return
    if a.user_data and not os.path.isfile(a.user_data):
        p.error(f"user data file not found: {a.user_data}")
    fields = [f.strip() for f in a.fields.split(",") if f.strip()]
    bad = [f for f in fields if f not in OMNI2_FIELDS]
    if bad:
        p.error(f"unknown quantity {bad}; see --list-fields")
    xlsx_only = a.out.lower().endswith(".xlsx")
    if a.excel or xlsx_only:
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            p.error("Excel output needs the openpyxl package:  python -m pip install openpyxl")
    out_dir, name = os.path.split(os.path.abspath(a.out))
    params = {"start": a.start, "end": a.end, "data": a.data, "refresh": a.refresh, "rule": a.rule,
              "min_hours": a.min_hours, "min_agreement": 100.0 * a.min_agreement, "out_dir": out_dir,
              "name": os.path.splitext(name)[0], "csv": not xlsx_only, "excel": a.excel or xlsx_only,
              "fields": fields, "user_file": a.user_data or None, "missing": a.missing, "min_days": a.min_days}
    res = run_job(params, log=lambda m: None)
    print(f"{res['days']} days with IMF data; T {res['T']}, A {res['A']}, unlabelled {res['unlabelled']} -> "
          + ", ".join(res["outputs"]))

if __name__ == "__main__":
    main()
