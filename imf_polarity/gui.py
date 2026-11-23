"""Desktop window for imf_polarity.  Start with:  python -m imf_polarity.gui"""
import datetime as dt
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import OMNI2_FIELDS, daily_means, read_user_data
from .plots import plot_ta
from .workflow import Cancelled, run_job

THIS_YEAR = dt.date.today().year
PRESETS = {
    "Default (half-plane, 12 h, 75 %)": ("halfplane", 12, 75),
    "Strict (half-plane, 12 h, 90 %)": ("halfplane", 12, 90),
    "OMNIWeb table (quadrant, 12 h, no agreement test)": ("quadrant", 12, 0),
    "Custom": None,
}
RULE_NAMES = {"Half-plane (45/225 deg boundary)": "halfplane", "Quadrant (OMNIWeb table)": "quadrant"}
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".imf_polarity_gui.json")
SAVED_KEYS = ("start", "end", "preset", "rule", "min_hours", "min_agreement", "data", "out_dir", "name",
              "csv", "excel", "min_days", "user_file", "missing")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SEASON_ORDER = ["DJF", "MAM", "JJA", "SON"]


class Tooltip:
    """Small help text shown while the mouse rests on a widget."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", background="#ffffe0", relief="solid", borderwidth=1,
                 wraplength=380, padx=6, pady=4).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def check_user_file(path, missing=None):
    """Short report on a user data file: columns, dates, counts. Used by the 'Check file' button."""
    raw = read_user_data(path, missing)
    daily = daily_means(raw)
    per_day = raw.groupby(raw.time.dt.normalize()).size()
    lines = [f"File: {os.path.basename(path)}",
             f"Rows read: {len(raw)}   dates: {raw.time.min():%Y-%m-%d} to {raw.time.max():%Y-%m-%d}",
             f"Values per day: {'1 (daily data)' if per_day.max() == 1 else f'up to {per_day.max()} (averaged to daily)'}",
             f"Days after daily averaging: {len(daily)}", ""]
    for c in raw.columns[1:]:
        v = raw[c]
        pos = "never negative, ATA computed" if v.notna().any() and (v.dropna() >= 0).all() else "takes negative values, no ATA"
        lines.append(f"{c}: {v.notna().sum()} values, {v.isna().sum()} missing, "
                     f"min {v.min():.4g}, max {v.max():.4g}  ({pos})")
    return "\n".join(lines)


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=8)
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self.stop = threading.Event()
        self.result = None
        self.excel_path = None
        root.title("IMF polarity - daily toward/away days from OMNI2")
        root.minsize(700, 560)
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        here = os.getcwd()
        self.v = {
            "start": tk.IntVar(value=1963), "end": tk.IntVar(value=THIS_YEAR),
            "preset": tk.StringVar(value=next(iter(PRESETS))),
            "rule": tk.StringVar(value=next(iter(RULE_NAMES))),
            "min_hours": tk.IntVar(value=12), "min_agreement": tk.IntVar(value=75),
            "data": tk.StringVar(value=os.path.join(here, "omni2_hourly")),
            "out_dir": tk.StringVar(value=here), "name": tk.StringVar(value="results"),
            "csv": tk.BooleanVar(value=True), "excel": tk.BooleanVar(value=True), "refresh": tk.BooleanVar(value=False),
            "min_days": tk.IntVar(value=3), "user_file": tk.StringVar(value=""), "missing": tk.StringVar(value=""),
            "plot_quantity": tk.StringVar(value=""),
        }
        self.saved_fields = []
        self._load_settings()
        self._build()
        root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._poll)

    # ---------- settings memory
    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                s = json.load(f)
        except (OSError, ValueError):
            return
        for k in SAVED_KEYS:
            if k in s:
                try:
                    self.v[k].set(s[k])
                except (tk.TclError, TypeError):
                    pass
        self.saved_fields = [x for x in s.get("fields", []) if x in OMNI2_FIELDS]

    def _save_settings(self):
        s = {}
        for k in SAVED_KEYS:
            try:
                s[k] = self.v[k].get()
            except tk.TclError:
                pass
        names = list(OMNI2_FIELDS)
        s["fields"] = [names[i] for i in self.w_fields.curselection()]
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=1)
        except OSError:
            pass

    def _close(self):
        self._save_settings()
        self.root.destroy()

    # ---------- layout
    def _build(self):
        self.nb = ttk.Notebook(self)
        self.nb.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.tab_pol, self.tab_q, self.tab_out, self.tab_res = (ttk.Frame(self.nb, padding=10) for _ in range(4))
        for t, name in ((self.tab_pol, "1  Polarity"), (self.tab_q, "2  Quantities"),
                        (self.tab_out, "3  Output"), (self.tab_res, "4  Results")):
            self.nb.add(t, text=name)
        self._build_polarity()
        self._build_quantities()
        self._build_output()
        self._build_results()

        b = ttk.Frame(self)
        b.grid(row=1, column=0, sticky="ew", pady=(8, 2))
        self.w_run = ttk.Button(b, text="Run", command=self._run)
        self.w_run.pack(side="left")
        self.w_cancel = ttk.Button(b, text="Cancel", command=self._cancel, state="disabled")
        self.w_cancel.pack(side="left", padx=6)
        ttk.Button(b, text="Open output folder", command=self._open_out).pack(side="left", padx=6)
        self.w_open_xlsx = ttk.Button(b, text="Open Excel file", command=self._open_excel, state="disabled")
        self.w_open_xlsx.pack(side="left")
        ttk.Button(b, text="About the method", command=self._about).pack(side="left", padx=6)
        self.w_bar = ttk.Progressbar(b, mode="determinate", length=150)
        self.w_bar.pack(side="right")

        lf = ttk.Frame(self)
        lf.grid(row=2, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        self.w_log = tk.Text(lf, height=6, wrap="word", state="disabled")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.w_log.yview)
        self.w_log.config(yscrollcommand=sb.set)
        self.w_log.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._log("Choose the settings in tabs 1-3 and press Run. The first run downloads about 3 MB per year from NASA.")

    def _note(self, parent, text, row, col=0, span=4):
        ttk.Label(parent, text=text, foreground="gray", justify="left", wraplength=620).grid(
            row=row, column=col, columnspan=span, sticky="w", pady=(0, 6))

    def _build_polarity(self):
        t = self.tab_pol
        t.columnconfigure(1, weight=1)
        ttk.Label(t, text="First year").grid(row=0, column=0, sticky="w")
        g = ttk.Frame(t)
        g.grid(row=0, column=1, sticky="w")
        w1 = ttk.Spinbox(g, from_=1963, to=THIS_YEAR, width=7, textvariable=self.v["start"])
        w1.pack(side="left")
        ttk.Label(g, text="   Last year").pack(side="left")
        w2 = ttk.Spinbox(g, from_=1963, to=THIS_YEAR, width=7, textvariable=self.v["end"])
        w2.pack(side="left", padx=6)
        self._note(t, "OMNI2 hourly data start on 1963-11-27.", 1, 1, 3)
        Tooltip(w1, "Years of OMNI2 data to download and classify.")

        ttk.Separator(t).grid(row=2, column=0, columnspan=4, sticky="ew", pady=6)
        ttk.Label(t, text="Setting").grid(row=3, column=0, sticky="w")
        cb = ttk.Combobox(t, values=list(PRESETS), textvariable=self.v["preset"], state="readonly")
        cb.grid(row=3, column=1, sticky="ew", pady=3)
        cb.bind("<<ComboboxSelected>>", self._apply_preset)
        Tooltip(cb, "Default: best balance of accuracy and number of days.\nStrict: fewer misclassified days, "
                    "fewer days kept.\nOMNIWeb table: reproduces NASA's daily polarity table.")
        ttk.Label(t, text="Rule").grid(row=4, column=0, sticky="w")
        self.w_rule = ttk.Combobox(t, values=list(RULE_NAMES), textvariable=self.v["rule"], state="readonly")
        self.w_rule.grid(row=4, column=1, sticky="ew", pady=3)
        self._note(t, "Half-plane: T if the daily field azimuth is 225-45 deg, A otherwise (boundary perpendicular "
                      "to the Parker spiral). Quadrant: T 270-360 deg, A 90-180 deg, no label in between.", 5, 1, 3)
        ttk.Label(t, text="Minimum hours per day").grid(row=6, column=0, sticky="w")
        self.w_hours = ttk.Spinbox(t, from_=1, to=24, width=6, textvariable=self.v["min_hours"])
        self.w_hours.grid(row=6, column=1, sticky="w", pady=3)
        ttk.Label(t, text="Minimum hour agreement (%)").grid(row=7, column=0, sticky="w")
        self.w_agr = ttk.Spinbox(t, from_=0, to=100, increment=5, width=6, textvariable=self.v["min_agreement"])
        self.w_agr.grid(row=7, column=1, sticky="w", pady=3)
        self._note(t, "Share of the day's hours that must have the same polarity as the day. It removes days with a "
                      "sector boundary or a mixed field. 0 % switches the test off.", 8, 1, 3)
        Tooltip(self.w_hours, "A day needs at least this many hours with both Bx and By.")
        for w in (self.w_rule, self.w_hours, self.w_agr):
            w.bind("<<ComboboxSelected>>", lambda e: self._maybe_custom(), add="+")
            w.bind("<KeyRelease>", lambda e: self._maybe_custom(), add="+")
            w.bind("<ButtonRelease-1>", lambda e: self._maybe_custom(), add="+")

    def _build_quantities(self):
        t = self.tab_q
        t.columnconfigure(1, weight=1)
        self._note(t, "Optional. Choose OMNI2 quantities and/or your own data file. Each is averaged per UT day and "
                      "sorted into T and A by month of each year, by calendar month and by season.", 0, 0, 4)
        ttk.Label(t, text="OMNI2 quantities").grid(row=1, column=0, sticky="nw")
        lf = ttk.Frame(t)
        lf.grid(row=1, column=1, sticky="ew", pady=3)
        self.w_fields = tk.Listbox(lf, selectmode="extended", height=9, exportselection=False)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.w_fields.yview)
        self.w_fields.config(yscrollcommand=sb.set)
        self.w_fields.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        names = list(OMNI2_FIELDS)
        for name, (col, fill, unit, _) in OMNI2_FIELDS.items():
            self.w_fields.insert("end", f"{name}  ({unit})")
        for f in self.saved_fields:
            self.w_fields.selection_set(names.index(f))
        ttk.Button(t, text="Clear", command=lambda: self.w_fields.selection_clear(0, "end")).grid(
            row=1, column=2, sticky="n", padx=6)
        self._note(t, "Only quantities with a known physical link to polarity (Russell-McPherron effect) are listed. "
                      "Ctrl+click to choose several.", 2, 1, 3)

        ttk.Separator(t).grid(row=3, column=0, columnspan=4, sticky="ew", pady=6)
        ttk.Label(t, text="Your own data file").grid(row=4, column=0, sticky="w")
        ttk.Entry(t, textvariable=self.v["user_file"]).grid(row=4, column=1, sticky="ew", pady=3)
        g = ttk.Frame(t)
        g.grid(row=4, column=2, sticky="w")
        ttk.Button(g, text="Browse...", command=self._browse_file).pack(side="left", padx=(6, 0))
        ttk.Button(g, text="Check file", command=self._check_file).pack(side="left", padx=6)
        g = ttk.Frame(t)
        g.grid(row=5, column=1, sticky="w")
        ttk.Label(g, text="Missing-value code").pack(side="left")
        wm = ttk.Entry(g, textvariable=self.v["missing"], width=8)
        wm.pack(side="left", padx=6)
        Tooltip(wm, "Number used for missing values in your file, e.g. -999. Empty cells are always missing.")
        self._note(t, ".csv or .xlsx; first column date or date-time (UT), other columns values, names in row 1. "
                      "A T-A difference in your data is not proof of a polarity effect: the dominant polarity seen "
                      "from Earth changes with season and solar cycle (Rosenberg-Coleman effect).", 6, 1, 3)
        self.w_check = tk.Text(t, height=6, wrap="none", state="disabled", background="#f6f6f6")
        self.w_check.grid(row=7, column=1, columnspan=2, sticky="ew")

        ttk.Separator(t).grid(row=8, column=0, columnspan=4, sticky="ew", pady=6)
        ttk.Label(t, text="Min days per polarity in a month").grid(row=9, column=0, sticky="w")
        wd = ttk.Spinbox(t, from_=1, to=31, width=6, textvariable=self.v["min_days"])
        wd.grid(row=9, column=1, sticky="w")
        Tooltip(wd, "A month of a given year is left empty when it has fewer days of a polarity. "
                    "Default 3 (tested: best seasonal precision at 3-5 days). The calendar-month and season "
                    "tables pool all days and do not use it.")

    def _build_output(self):
        t = self.tab_out
        t.columnconfigure(1, weight=1)
        for r, (key, label) in enumerate([("data", "OMNI2 data folder"), ("out_dir", "Output folder")]):
            ttk.Label(t, text=label).grid(row=r, column=0, sticky="w")
            ttk.Entry(t, textvariable=self.v[key]).grid(row=r, column=1, sticky="ew", pady=3)
            ttk.Button(t, text="Browse...", command=lambda k=key: self._browse(k)).grid(row=r, column=2, padx=6)
        ttk.Label(t, text="Output file name").grid(row=2, column=0, sticky="w")
        ttk.Entry(t, textvariable=self.v["name"], width=28).grid(row=2, column=1, sticky="w", pady=3)
        g = ttk.Frame(t)
        g.grid(row=3, column=1, sticky="w", pady=6)
        ttk.Checkbutton(g, text="CSV", variable=self.v["csv"]).pack(side="left")
        ttk.Checkbutton(g, text="Excel (.xlsx)", variable=self.v["excel"]).pack(side="left", padx=12)
        wr = ttk.Checkbutton(t, text="Download the latest data again (refresh)", variable=self.v["refresh"])
        wr.grid(row=4, column=1, sticky="w")
        Tooltip(wr, "NASA revises the current and recent years. Tick this to replace files already downloaded.")
        self._note(t, "Excel sheets: Polarity, Data (all daily values, not split), Monthly, Calendar months, Seasons, "
                      "Settings. The same tables are written as CSV files. Without chosen quantities only the polarity "
                      "file is written. Settings are remembered for the next session.", 5, 0, 3)

    def _build_results(self):
        t = self.tab_res
        t.columnconfigure(0, weight=1)
        t.rowconfigure(2, weight=1)
        self.w_summary = ttk.Label(t, text="No run yet.", justify="left")
        self.w_summary.grid(row=0, column=0, sticky="w")
        cols = ("quantity", "DJF", "MAM", "JJA", "SON", "T days", "A days")
        self.w_table = ttk.Treeview(t, columns=cols, show="headings", height=4)
        for c in cols:
            self.w_table.heading(c, text=c if c in ("quantity", "T days", "A days") else f"T-A {c}")
            self.w_table.column(c, width=150 if c == "quantity" else 80, anchor="w" if c == "quantity" else "e")
        self.w_table.grid(row=1, column=0, sticky="ew", pady=4)
        self.plot_frame = ttk.Frame(t)
        self.plot_frame.grid(row=2, column=0, sticky="nsew")
        g = ttk.Frame(t)
        g.grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(g, text="Plot quantity").pack(side="left")
        self.w_plotq = ttk.Combobox(g, textvariable=self.v["plot_quantity"], state="readonly", width=24)
        self.w_plotq.pack(side="left", padx=6)
        self.w_plotq.bind("<<ComboboxSelected>>", lambda e: self._draw())
        self.w_saveplot = ttk.Button(g, text="Save plot...", command=self._save_plot, state="disabled")
        self.w_saveplot.pack(side="left", padx=6)
        self.fig = self.canvas = None
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            self.fig = Figure(figsize=(7.2, 3.2), dpi=96)
            self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
            self.canvas.get_tk_widget().pack(fill="both", expand=True)
        except ImportError:
            ttk.Label(self.plot_frame, foreground="gray",
                      text="Plots need matplotlib:  python -m pip install matplotlib").pack(anchor="w")

    # ---------- results
    def _show_results(self, res):
        self.result = res
        txt = (f"{res['days']} days with IMF data ({res['first']} to {res['last']}):  "
               f"T {res['T']},  A {res['A']},  unlabelled {res['unlabelled']}")
        self.w_table.delete(*self.w_table.get_children())
        tabs = res.get("tables")
        names = []
        if tabs:
            se = tabs["Seasons"]
            names = [c[:-4] for c in se.columns if c.endswith("_T-A")]
            for n in names:
                vals = [se.loc[s, f"{n}_T-A"] for s in SEASON_ORDER]
                self.w_table.insert("", "end", values=[n] + [f"{x:.3g}" for x in vals]
                                    + [int(se[f"{n}_nT"].sum()), int(se[f"{n}_nA"].sum())])
            txt += "\nT-A by season below (all years pooled); plot: T-A by calendar month and by season."
        else:
            txt += "\nNo quantities were chosen (tab 2), so there is nothing to plot."
        self.w_summary.config(text=txt)
        self.w_plotq.config(values=names)
        if names:
            if self.v["plot_quantity"].get() not in names:
                self.v["plot_quantity"].set(names[0])
            self._draw()
        self.nb.select(self.tab_res)

    def _draw(self):
        if self.fig is None or not self.result or not self.result.get("tables"):
            return
        n = self.v["plot_quantity"].get()
        plot_ta(self.fig, self.result["tables"], n, f"{self.result['first'][:4]}-{self.result['last'][:4]}")
        self.canvas.draw()
        self.w_saveplot.config(state="normal")

    def _save_plot(self):
        if self.fig is None:
            return
        f = filedialog.asksaveasfilename(defaultextension=".png", initialdir=self.v["out_dir"].get(),
                                         initialfile=f"{self.v['name'].get()}_{self.v['plot_quantity'].get()}_TA.png",
                                         filetypes=[("PNG image", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")])
        if f:
            self.fig.savefig(f, dpi=300, bbox_inches="tight")
            self._log("Plot saved: " + f)

    # ---------- actions
    def _apply_preset(self, _=None):
        val = PRESETS.get(self.v["preset"].get())
        if val:
            rule, hours, agr = val
            self.v["rule"].set(next(k for k, x in RULE_NAMES.items() if x == rule))
            self.v["min_hours"].set(hours)
            self.v["min_agreement"].set(agr)

    def _maybe_custom(self):
        val = PRESETS.get(self.v["preset"].get())
        try:
            now = (RULE_NAMES[self.v["rule"].get()], self.v["min_hours"].get(), self.v["min_agreement"].get())
        except (tk.TclError, KeyError):
            return
        if val and now != val:
            self.v["preset"].set("Custom")

    def _browse(self, key):
        d = filedialog.askdirectory(initialdir=self.v[key].get() or os.getcwd())
        if d:
            self.v[key].set(d)

    def _browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.txt *.xlsx *.xls"), ("All files", "*.*")])
        if f:
            self.v["user_file"].set(f)
            self._check_file()

    def _check_file(self):
        path = self.v["user_file"].get().strip()
        try:
            if not path:
                raise ValueError("Choose a file first.")
            m = self.v["missing"].get().strip()
            report = check_user_file(path, float(m) if m else None)
        except Exception as e:  # show any reading problem to the user
            report = f"Problem with the file: {e}"
        self.w_check.config(state="normal")
        self.w_check.delete("1.0", "end")
        self.w_check.insert("end", report)
        self.w_check.config(state="disabled")

    def _open_path(self, path):
        if sys.platform.startswith("win"):
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])

    def _open_out(self):
        d = self.v["out_dir"].get()
        if os.path.isdir(d):
            self._open_path(d)

    def _open_excel(self):
        if self.excel_path and os.path.isfile(self.excel_path):
            self._open_path(self.excel_path)

    def _about(self):
        messagebox.showinfo("About the method", (
            "Each day is labelled from the azimuth phi = atan2(By, Bx) of its mean IMF vector (GSE).\n\n"
            "Half-plane rule: toward (T) if phi >= 225 or phi < 45 deg, away (A) otherwise. "
            "The 45/225 deg line is perpendicular to the mean Parker spiral.\n\n"
            "Quadrant rule: T if 270-360 deg, A if 90-180 deg, no label in the other quadrants "
            "(the rule of the OMNIWeb polarity table).\n\n"
            "A day is kept when it has at least the minimum number of hours, and when the share of hours "
            "with the same half-plane polarity as the day reaches the minimum agreement.\n\n"
            "Geomagnetic quantities respond to polarity through the Russell-McPherron effect: toward days are "
            "more active in spring and away days in autumn, so results are given by month, calendar month and "
            "season, not by year.\n\n"
            "Data: NASA GSFC SPDF OMNI2 hourly files (King and Papitashvili, 2005)."))

    def _params(self):
        try:
            p = {k: var.get() for k, var in self.v.items()}
        except tk.TclError:
            raise ValueError("Years, hours, agreement and days must be whole numbers.")
        p["rule"] = RULE_NAMES[p["rule"]]
        if not 1963 <= p["start"] <= THIS_YEAR or not 1963 <= p["end"] <= THIS_YEAR:
            raise ValueError(f"Years must be between 1963 and {THIS_YEAR}.")
        if not 1 <= p["min_hours"] <= 24:
            raise ValueError("Minimum hours must be between 1 and 24.")
        if not 0 <= p["min_agreement"] <= 100:
            raise ValueError("Minimum agreement must be between 0 and 100 %.")
        if not p["name"].strip():
            raise ValueError("Give an output file name (tab 3).")
        p["name"] = os.path.splitext(p["name"].strip())[0]
        names = list(OMNI2_FIELDS)
        p["fields"] = [names[i] for i in self.w_fields.curselection()]
        if not 1 <= p["min_days"] <= 31:
            raise ValueError("Minimum days per polarity must be between 1 and 31.")
        p["user_file"] = p["user_file"].strip() or None
        if p["user_file"] and not os.path.isfile(p["user_file"]):
            raise ValueError("The user data file was not found (tab 2).")
        m = p["missing"].strip()
        try:
            p["missing"] = float(m) if m else None
        except ValueError:
            raise ValueError("The missing-value code must be a number (or empty).")
        return p

    def _run(self):
        if self.busy:
            return
        try:
            p = self._params()
        except ValueError as e:
            messagebox.showerror("Check the settings", str(e))
            return
        self._save_settings()
        self.busy = True
        self.stop.clear()
        self.w_run.config(state="disabled")
        self.w_cancel.config(state="normal")
        self.w_bar["value"] = 0
        self._log(f"--- Run: {p['start']}-{p['end']}, rule {p['rule']}, >= {p['min_hours']} h, "
                  f">= {p['min_agreement']} % agreement"
                  + (f"; OMNI2: {', '.join(p['fields'])}" if p["fields"] else "")
                  + (f"; file: {os.path.basename(p['user_file'])}" if p["user_file"] else ""))

        def work():
            try:
                res = run_job(p, lambda m: self.q.put(("log", m)), lambda d, t: self.q.put(("bar", 100 * d / t)),
                              should_stop=self.stop.is_set)
                self.q.put(("done", res))
            except Cancelled as e:
                self.q.put(("cancelled", str(e)))
            except Exception as e:  # report every failure in the window
                self.q.put(("error", f"{type(e).__name__}: {e}"))

        threading.Thread(target=work, daemon=True).start()

    def _cancel(self):
        if self.busy:
            self.stop.set()
            self._log("Stopping after the current step ...")

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self._log(val)
                elif kind == "bar":
                    self.w_bar["value"] = val
                elif kind == "done":
                    self._log(f"Done. T {val['T']}, A {val['A']}, unlabelled {val['unlabelled']}.")
                    for o in val["outputs"]:
                        self._log("Saved: " + o)
                    xl = [o for o in val["outputs"] if o.endswith(".xlsx")]
                    self.excel_path = xl[0] if xl else None
                    self.w_open_xlsx.config(state="normal" if xl else "disabled")
                    self._show_results(val)
                    self._finish()
                elif kind == "cancelled":
                    self._log(val)
                    self._finish()
                elif kind == "error":
                    self._log("Error: " + val)
                    messagebox.showerror("Run failed", val)
                    self._finish()
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _finish(self):
        self.busy = False
        self.w_run.config(state="normal")
        self.w_cancel.config(state="disabled")

    def _log(self, msg):
        self.w_log.config(state="normal")
        self.w_log.insert("end", msg + "\n")
        self.w_log.see("end")
        self.w_log.config(state="disabled")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
