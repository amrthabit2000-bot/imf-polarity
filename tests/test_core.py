"""Known-answer tests. Run with:  python -m pytest tests"""
import os

import numpy as np
import pandas as pd

from imf_polarity import asymmetry, classify, daily_polarity, sort_by_polarity, to_excel


def _vec(phi_deg, b=5.0):
    r = np.radians(phi_deg)
    return b * np.cos(r), b * np.sin(r)


def test_halfplane_boundaries():
    phi = [0, 44.9, 45, 135, 224.9, 225, 315, 359.9]
    assert list(classify(phi)) == ["T", "T", "A", "A", "A", "T", "T", "T"]


def test_quadrant_boundaries():
    # toward = [270, 360), away = [90, 180)
    phi = [0, 89.9, 90, 135, 179.9, 180, 269.9, 270, 315]
    assert list(classify(phi, "quadrant")) == ["", "", "A", "A", "A", "", "", "T", "T"]


def test_spiral_directions():
    # toward field along the nominal Parker spiral: Bx > 0, By < 0 (phi = 315 deg); away: Bx < 0, By > 0
    assert classify([np.degrees(np.arctan2(-1, 1)) % 360])[0] == "T"
    assert classify([np.degrees(np.arctan2(1, -1)) % 360])[0] == "A"


def _day(angles, date="2000-01-01"):
    t = pd.Timestamp(date) + pd.to_timedelta(range(len(angles)), unit="h")
    bx, by = _vec(np.asarray(angles, float))
    return pd.DataFrame({"time": t, "Bx": bx, "By": by})


def test_agreement_threshold():
    d18 = daily_polarity(_day([315] * 18 + [135] * 6))   # 75 % of hours toward -> kept
    d17 = daily_polarity(_day([315] * 17 + [135] * 7))   # 71 % -> dropped
    assert d18.polarity.iloc[0] == "T" and abs(d18.agreement.iloc[0] - 0.75) < 1e-12
    assert d17.polarity.iloc[0] == "" and d17.polarity_raw.iloc[0] == "T"


def test_min_hours():
    assert daily_polarity(_day([135] * 11)).polarity.iloc[0] == ""
    assert daily_polarity(_day([135] * 12)).polarity.iloc[0] == "A"


def test_quadrant_drops_off_spiral_day():
    d = daily_polarity(_day([20] * 24), rule="quadrant")   # azimuth 20 deg: toward by halfplane, mixed by quadrant
    assert d.polarity.iloc[0] == "" and daily_polarity(_day([20] * 24)).polarity.iloc[0] == "T"


def test_missing_hours_ignored():
    h = _day([315] * 24)
    h.loc[:9, ["Bx", "By"]] = np.nan
    d = daily_polarity(h)
    assert d.n_hours.iloc[0] == 14 and d.polarity.iloc[0] == "T"


def test_recovers_planted_difference():
    # synthetic year: index is 20 on toward days and 10 on away days -> monthly T = 20, A = 10 exactly;
    # with no planted difference both must be equal
    rng = np.random.default_rng(1)
    days = pd.date_range("2001-01-01", "2001-12-31")
    pol = pd.Series(rng.choice(["T", "A"], len(days)), index=days)
    for effect in (0.0, 10.0):
        x = pd.Series(np.where(pol == "T", 10.0 + effect, 10.0), index=days)
        m = sort_by_polarity(x, pol)
        assert np.allclose(m["T"] - m["A"], effect)
    ata, lnr = asymmetry([20.0], [10.0])
    assert abs(ata[0] - 1 / 3) < 1e-12 and abs(lnr[0] - np.log(2)) < 1e-12


def test_min_days_per_month():
    days = pd.date_range("2001-01-01", "2001-01-31")
    pol = pd.Series(["A"] * 29 + ["T"] * 2, index=days)
    m = sort_by_polarity(pd.Series(1.0, index=days), pol)
    assert np.isnan(m["T"].iloc[0]) and m["n_T"].iloc[0] == 2 and m["A"].iloc[0] == 1.0


def test_excel_round_trip(tmp_path):
    hours = pd.date_range("2020-01-01", periods=72, freq="h")
    phi = [315] * 24 + [135] * 24 + [315] * 12 + [135] * 12      # T day, A day, mixed day
    bx, by = _vec(np.array(phi, float))
    d = daily_polarity(pd.DataFrame({"time": hours, "Bx": bx, "By": by}))
    path = tmp_path / "out.xlsx"
    to_excel(d, path, {"rule": "halfplane"})
    x = pd.read_excel(path, sheet_name="Polarity")
    assert list(x.columns) == ["date"] + list(d.columns)
    assert list(x.polarity.fillna("")) == ["T", "A", ""]
    assert list(x.n_hours) == [24, 24, 24]
    s = pd.read_excel(path, sheet_name="Settings", index_col=0)["value"]
    assert s["rule"] == "halfplane" and int(s["T days"]) == 1 and int(s["unlabelled days"]) == 1


def test_gui_run_job(tmp_path):
    """The window's run function on a synthetic OMNI2 file: one T day, one A day, one mixed day."""
    from imf_polarity.gui import run_job
    data = tmp_path / "data"
    data.mkdir()
    phi = [315] * 24 + [135] * 24 + [315] * 12 + [135] * 12
    bx, by = _vec(np.array(phi, float))
    rows = []
    for k in range(72):
        r = ["0"] * 55
        r[0], r[1], r[2] = "2020", str(1 + k // 24), str(k % 24)
        r[12], r[13], r[24] = f"{bx[k]:.1f}", f"{by[k]:.1f}", "400."
        rows.append(" ".join(r))
    (data / "omni2_2020.dat").write_text("\n".join(rows) + "\n")
    p = {"start": 2020, "end": 2020, "data": str(data), "refresh": False, "rule": "halfplane", "min_hours": 12,
         "min_agreement": 75, "out_dir": str(tmp_path / "out"), "name": "test", "csv": True, "excel": True}
    res = run_job(p, log=lambda m: None)
    assert (res["T"], res["A"], res["unlabelled"]) == (1, 1, 1)
    assert [os.path.basename(o) for o in res["outputs"]] == ["test.csv", "test.xlsx"]
    assert list(pd.read_csv(res["outputs"][0]).polarity.fillna("")) == ["T", "A", ""]


def _omni_file(path, phi, extra):
    """Synthetic OMNI2 file: 24 h per day, azimuth list ``phi``, extra = {column: hourly values}."""
    bx, by = _vec(np.array(phi, float))
    rows = []
    for k in range(len(phi)):
        r = ["0"] * 55
        r[0], r[1], r[2] = "2020", str(1 + k // 24), str(k % 24)
        r[12], r[13], r[24] = f"{bx[k]:.1f}", f"{by[k]:.1f}", "400."
        for col, vals in extra.items():
            r[col] = str(vals[k])
        rows.append(" ".join(r))
    path.write_text("\n".join(rows) + "\n")


def test_sort_fields_known_answer(tmp_path):
    """Dst -20 nT on the T day and -40 nT on the A day (one fill hour); Kp*10 30 and 20."""
    from imf_polarity import daily_means, read_omni2_fields, read_omni2_hourly, sort_fields
    phi = [315] * 24 + [135] * 24
    f = tmp_path / "omni2_2020.dat"
    _omni_file(f, phi, {40: [-20] * 24 + [-40] * 23 + [99999], 38: [30] * 24 + [20] * 24})
    days = daily_polarity(read_omni2_hourly([f]))
    daily = daily_means(read_omni2_fields([f], ["Dst", "Kp_x10"]))
    tab = sort_fields(daily, days.polarity, min_days=1)
    assert set(tab) == {"Monthly", "Calendar months", "Seasons"}
    m = tab["Monthly"].iloc[0]
    assert (m["Dst_T"], m["Dst_A"], m["Dst_T-A"]) == (-20, -40, 20)
    assert "Dst_ATA" not in tab["Monthly"].columns              # Dst can be negative: no ratio index
    assert abs(m["Kp_x10_ATA"] - 10 / 50) < 1e-12
    c = tab["Calendar months"]
    assert c.loc["Jan", "Dst_T"] == -20 and c.loc["Feb", "Dst_nT"] == 0
    assert tab["Seasons"].loc["DJF", "Kp_x10_A"] == 20 and tab["Seasons"].loc["MAM", "Kp_x10_nA"] == 0
    tab2 = sort_fields(daily, days.polarity, min_days=2)          # one day of each: monthly value removed
    assert np.isnan(tab2["Monthly"]["Dst_T"].iloc[0])
    assert tab2["Calendar months"].loc["Jan", "Dst_T"] == -20    # pooled tables use every day


def test_user_data_file(tmp_path):
    """User file with a missing-value code; positive quantity gets ATA automatically."""
    from imf_polarity import daily_means, read_user_data, sort_fields
    f = tmp_path / "ssn.csv"
    f.write_text("date,SSN,Q,Z\n2020-01-01,100,-5,0\n2020-01-02,50,-1,0\n2020-01-03,-999,2,0\n")
    u = read_user_data(f, missing=-999)
    assert list(u.columns) == ["time", "SSN", "Q", "Z"] and np.isnan(u.SSN.iloc[2])
    pol = pd.Series(["T", "A", "T"], index=pd.date_range("2020-01-01", periods=3, freq="D"))
    tab = sort_fields(daily_means(u), pol, min_days=1)
    c = tab["Calendar months"].loc["Jan"]
    assert (c["SSN_T"], c["SSN_A"], c["SSN_nT"]) == (100, 50, 1)
    assert abs(c["SSN_ATA"] - 50 / 150) < 1e-12
    assert "Q_ATA" not in tab["Calendar months"].columns and c["Q_T"] == -1.5
    assert np.isnan(c["Z_ATA"])                                   # never negative, but T + A = 0: no ratio


def test_workflow_with_fields(tmp_path):
    from imf_polarity.workflow import run_job
    data = tmp_path / "data"
    data.mkdir()
    _omni_file(data / "omni2_2020.dat", [315] * 24 + [135] * 24, {40: [-20] * 24 + [-40] * 24})
    uf = tmp_path / "mine.xlsx"
    pd.DataFrame({"date": pd.to_datetime(["2020-01-01", "2020-01-02"]), "X": [3.0, 1.0]}).to_excel(uf, index=False)
    p = {"start": 2020, "end": 2020, "data": str(data), "refresh": False, "rule": "halfplane", "min_hours": 12,
         "min_agreement": 75, "out_dir": str(tmp_path / "out"), "name": "r", "csv": True, "excel": True,
         "fields": ["Dst"], "user_file": str(uf), "min_days": 1}
    res = run_job(p, log=lambda m: None)
    names = [os.path.basename(o) for o in res["outputs"]]
    assert names == ["r.csv", "r_data.csv", "r_monthly.csv", "r_calendar_months.csv", "r_seasons.csv", "r.xlsx"]
    x = pd.read_excel(res["outputs"][-1], sheet_name=None)
    assert list(x) == ["Polarity", "Data", "Monthly", "Calendar months", "Seasons", "Settings"]
    assert list(x["Data"]["polarity"]) == ["T", "A"] and list(x["Data"]["Dst"]) == [-20, -40] and list(x["Data"]["X"]) == [3, 1]
    assert x["Calendar months"]["X_T"].iloc[0] == 3 and x["Calendar months"]["Dst_A"].iloc[0] == -40


def test_check_user_file(tmp_path):
    from imf_polarity.gui import check_user_file
    f = tmp_path / "hourly.csv"
    f.write_text("time,X,Y\n2020-01-01 00:00,1,-1\n2020-01-01 12:00,3,2\n2020-01-02 00:00,-999,4\n")
    rep = check_user_file(f, missing=-999)
    assert "up to 2 (averaged to daily)" in rep and "Days after daily averaging: 2" in rep
    assert "X: 2 values, 1 missing" in rep and "never negative" in rep.split("X:")[1].split("\n")[0]
    assert "no ATA" in rep.split("Y:")[1]


def test_yearly_intervals():
    """Two years with January T-A of 1 and 3: half-width = t(0.975, 1) * sd / sqrt(2) = 12.71."""
    from imf_polarity import yearly_intervals
    idx = pd.to_datetime(["2001-01-01", "2002-01-01", "2001-04-01", "2002-04-01", "2003-04-01"])
    monthly = pd.DataFrame({"X_T-A": [1.0, 3.0, 2.0, 2.0, 2.0]}, index=idx)
    cm, se = yearly_intervals(monthly, "X")
    assert abs(cm[0] - 12.71) < 1e-9 and cm[3] == 0 and np.isnan(cm[1])
    assert abs(se[0] - 12.71) < 1e-9 and se[1] == 0               # DJF from January; MAM from April
