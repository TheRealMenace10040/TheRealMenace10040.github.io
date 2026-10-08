"""From raw sewershed samples to one weekly wastewater level per virus, nationally and by state.

Raw concentrations can't be compared across sites: every plant has its own
flow, population, lab and method. So each site is put on its own scale first,
the same idea as CDC's Wastewater Viral Activity Level:

    site level = (log10 concentration - site's 10th percentile) / site's standard deviation

A level of 0 is a quiet week for that site, and each +1 is one standard
deviation above it. The national and state levels are the median across the
sites reporting that week.
"""
import numpy as np
import pandas as pd

MIN_SITE_WEEKS = 26      # a site needs half a year of data before its baseline means anything
MIN_SITES_US = 30
MIN_SITES_STATE = 3


def week_ending(dates):
    """MMWR week ending Saturday, the same weeks CDC uses for ED visit data."""
    return (dates + pd.to_timedelta((5 - dates.dt.weekday) % 7, unit="D")).dt.normalize()


def read_samples(path, virus, states):
    """states maps full state names and abbreviations to two-letter abbreviations."""
    d = pd.read_csv(path, dtype={"site": str, "state": str})
    n0 = len(d)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["conc"] = pd.to_numeric(d["conc"], errors="coerce")
    d["state"] = d["state"].str.strip().map(lambda s: states.get(s, states.get(str(s).upper())))
    d = d.dropna(subset=["site", "state", "date", "conc"])
    d = d[(d["conc"] >= 0) & (d["date"] >= "2020-01-01")]
    print(f"{virus}: {len(d):,} of {n0:,} samples kept, {d['site'].nunique():,} sites")
    return d.assign(virus=virus)[["virus", "site", "state", "date", "conc"]]


def site_weeks(samples):
    """One row per virus, site and week, with the site-standardized level."""
    d = samples.copy()
    # Non-detects (0) get half the site's lowest detected value, so the log is defined.
    floor = d[d["conc"] > 0].groupby(["virus", "site"])["conc"].min().rename("floor") / 2
    d = d.join(floor, on=["virus", "site"])
    d = d[d["floor"].notna()]
    d["log"] = np.log10(d["conc"].where(d["conc"] > 0, d["floor"]))
    d["week"] = week_ending(d["date"])

    w = (d.groupby(["virus", "site", "state", "week"], as_index=False)
           .agg(log=("log", "mean"), samples=("log", "size")))
    n = w.groupby(["virus", "site"])["week"].transform("size")
    w = w[n >= MIN_SITE_WEEKS].copy()

    g = w.groupby(["virus", "site"])["log"]
    p10 = g.transform(lambda s: s.quantile(0.10))
    sd = g.transform("std")
    w["level"] = (w["log"] - p10) / sd
    w = w[np.isfinite(w["level"])]
    print(w.groupby("virus")["site"].nunique().rename("sites with 26+ weeks").to_string())
    return w


def _drop_incomplete_tail(t, by):
    """The newest week is often still filling in. Drop trailing weeks with under 60% of the usual site count."""
    keep = []
    for _, g in t.groupby(by, sort=False):
        g = g.sort_values("date")
        usual = g["n_sites"].rolling(8, min_periods=4).median().shift(1)
        short = g["n_sites"] < 0.6 * usual
        end = len(g)
        while end > 0 and short.iloc[end - 1]:
            end -= 1
        keep.append(g.iloc[:end])
    return pd.concat(keep)


def aggregate(w):
    nat = (w.groupby(["virus", "week"])
             .agg(ww_level=("level", "median"), n_sites=("site", "nunique"))
             .reset_index().rename(columns={"week": "date"}))
    nat = nat[nat["n_sites"] >= MIN_SITES_US]
    nat = _drop_incomplete_tail(nat, "virus")

    st = (w.groupby(["virus", "state", "week"])
            .agg(ww_level=("level", "median"), n_sites=("site", "nunique"))
            .reset_index().rename(columns={"week": "date"}))
    st = st[st["n_sites"] >= MIN_SITES_STATE]
    st = _drop_incomplete_tail(st, ["virus", "state"])
    return nat.reset_index(drop=True), st.reset_index(drop=True)
