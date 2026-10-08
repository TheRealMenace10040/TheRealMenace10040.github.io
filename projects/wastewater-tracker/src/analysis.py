"""The three questions, answered on the weekly national and state series.

1. Lead time: does wastewater move before ED visits?
   - Cross-correlation of week-over-week changes (wastewater level vs log ED %)
     at lags of -4 to +6 weeks. Changes, not levels, so two series that both
     trend up don't look related just because they trend.
   - Wave by wave: for every wastewater peak, find the ED peak within 8 weeks
     and count the days between them.
2. Seasons: peak height and timing for each wave of each virus.
3. Forecast:
   - Wastewater level 4 weeks ahead with an ARIMA model (order picked by AIC),
     backtested against "next week = this week".
   - Does wastewater help forecast ED visits? A direct regression of the
     change in log ED % over the next h weeks, with and without recent
     wastewater changes, scored on a rolling backtest.
"""
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings("ignore")   # statsmodels convergence chatter on small grids

VIRUSES = ["covid", "flu", "rsv"]
ED_FLOOR = 0.005    # % of ED visits; weeks reported as 0 (small states, RSV off-season) get this so the log is defined
LAGS = range(-4, 7)
HORIZON = 4
BACKTEST_WEEKS = 52


def season_of(d):
    """Respiratory season, August to July (CDC's NWSS convention): 2024-08-03 -> '2024-25'."""
    y = d.year if d.month >= 8 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


# ---------- joining ----------

def join(ww, ed):
    e = ed.rename(columns={"value": "ed_pct"})
    return ww.merge(e, on=[c for c in ("virus", "state", "date") if c in ww.columns], how="outer")


# ---------- 1. lead time ----------

def xcorr(x, y, lags=LAGS):
    """corr(dx[t-k], dy[t]). Positive k: wastewater changes come k weeks before ED changes."""
    dx, dy = x.diff(), np.log(y.clip(lower=ED_FLOOR)).diff()
    out = []
    for k in lags:
        pair = pd.concat([dx.shift(k), dy], axis=1).dropna()
        out.append((k, pair.iloc[:, 0].corr(pair.iloc[:, 1]) if len(pair) > 20 else np.nan, len(pair)))
    return pd.DataFrame(out, columns=["lag_weeks", "corr", "n_weeks"])


def lag_tables(nat_j, st_j):
    nat_rows, st_rows = [], []
    for v in VIRUSES:
        s = nat_j[(nat_j.virus == v)].set_index("date").sort_index().dropna(subset=["ww_level", "ed_pct"])
        s = s.asfreq("7D")
        c = xcorr(s["ww_level"], s["ed_pct"]).assign(virus=v)
        nat_rows.append(c)
        for st, g in st_j[st_j.virus == v].groupby("state"):
            g = g.set_index("date").sort_index().dropna(subset=["ww_level", "ed_pct"])
            if len(g) < 52:
                continue
            g = g.asfreq("7D")
            c = xcorr(g["ww_level"], g["ed_pct"]).dropna()
            if c.empty:
                continue
            best = c.loc[c["corr"].idxmax()]
            st_rows.append({"virus": v, "state": st, "best_lag_weeks": int(best.lag_weeks),
                            "corr": best["corr"], "corr_lag0": c.set_index("lag_weeks")["corr"].get(0, np.nan),
                            "n_weeks": int(best.n_weeks)})
    return pd.concat(nat_rows)[["virus", "lag_weeks", "corr", "n_weeks"]], pd.DataFrame(st_rows)


def find_peaks(s, window=10, min_rise=1.0):
    """Local maxima of a 3-week centered mean: the highest point within +/- window weeks,
    and at least min_rise above the lowest point in the window before it."""
    sm3 = s.rolling(3, center=True, min_periods=2).mean()
    peaks = []
    for i in range(len(sm3)):
        lo, hi = max(0, i - window), min(len(sm3), i + window + 1)
        win = sm3.iloc[lo:hi]
        if sm3.iloc[i] == win.max() and sm3.iloc[i] - sm3.iloc[lo:i + 1].min() >= min_rise:
            peaks.append(sm3.index[i])
    return peaks, sm3


def wave_table(nat_j):
    rows = []
    for v in VIRUSES:
        s = nat_j[nat_j.virus == v].set_index("date").sort_index()
        ww = s["ww_level"].dropna().asfreq("7D").interpolate(limit=2)
        ed = s["ed_pct"].dropna().asfreq("7D")
        peaks, ww3 = find_peaks(ww)
        ed3 = ed.rolling(3, center=True, min_periods=2).mean()
        last = ww.index.max()
        for p in peaks:
            if p > last - pd.Timedelta(weeks=3):
                continue   # still rising or just turned: not a confirmed peak yet
            row = {"virus": v, "season": season_of(p), "ww_peak": p, "ww_peak_level": ww3[p]}
            near = ed3[(ed3.index >= p - pd.Timedelta(weeks=8)) & (ed3.index <= p + pd.Timedelta(weeks=8))].dropna()
            if len(near) >= 12 and near.idxmax() not in (near.index.min(), near.index.max()):
                row.update(ed_peak=near.idxmax(), ed_peak_pct=near.max(),
                           lead_days=(near.idxmax() - p).days)
            rows.append(row)
    w = pd.DataFrame(rows)
    for c in ("ed_peak", "ed_peak_pct", "lead_days"):
        if c not in w:
            w[c] = np.nan
    return w


# ---------- 3. forecasts ----------

def fit_arima(y):
    best = None
    for p in range(0, 4):
        for d in (0, 1):
            for q in (0, 1):
                try:
                    m = ARIMA(y.values, order=(p, d, q), trend="c" if d == 0 else "n").fit()
                except Exception:
                    continue
                if best is None or m.aic < best[1].aic:
                    best = ((p, d, q), m)
    return best


def ww_forecast(nat):
    fc_rows, bt_rows, orders = [], [], {}
    for v in VIRUSES:
        y = nat[nat.virus == v].set_index("date")["ww_level"].sort_index().asfreq("7D").interpolate(limit=2).dropna()
        y = y[y.index >= y.index.max() - pd.Timedelta(weeks=156)]          # last 3 years
        order, m = fit_arima(y)
        orders[v] = order
        f = m.get_forecast(HORIZON)
        ci = f.conf_int(alpha=0.2)
        for h in range(HORIZON):
            fc_rows.append({"virus": v, "date": y.index.max() + pd.Timedelta(weeks=h + 1),
                            "ww_level": f.predicted_mean[h], "lo80": ci[h, 0], "hi80": ci[h, 1]})
        # rolling-origin backtest with the chosen order
        errs = {h: [] for h in range(1, HORIZON + 1)}
        naive = {h: [] for h in range(1, HORIZON + 1)}
        n = len(y)
        for t in range(n - BACKTEST_WEEKS - HORIZON, n - 1):
            train = y.iloc[:t + 1]
            try:
                pred = ARIMA(train.values, order=order, trend="c" if order[1] == 0 else "n").fit().forecast(HORIZON)
            except Exception:
                continue
            for h in range(1, HORIZON + 1):
                if t + h < n:
                    errs[h].append(abs(pred[h - 1] - y.iloc[t + h]))
                    naive[h].append(abs(train.iloc[-1] - y.iloc[t + h]))
        for h in range(1, HORIZON + 1):
            bt_rows.append({"virus": v, "horizon_weeks": h, "mae_arima": np.mean(errs[h]),
                            "mae_naive": np.mean(naive[h]), "n": len(errs[h])})
    return pd.DataFrame(fc_rows), pd.DataFrame(bt_rows), orders


def ed_design(s, h, with_ww):
    """Target: change in log ED % from week t to t+h. Features known at week t."""
    ly = np.log(s["ed_pct"].clip(lower=ED_FLOOR))
    X = pd.DataFrame({"dy0": ly.diff(), "dy1": ly.diff().shift(1)}, index=s.index)
    if with_ww:
        X["dx0"] = s["ww_level"].diff()
        X["dx1"] = s["ww_level"].diff().shift(1)
        X["x0"] = s["ww_level"]
    X = sm.add_constant(X)
    target = ly.shift(-h) - ly
    return X, target, ly


def ed_backtest(nat_j):
    rows, fc_rows = [], []
    for v in VIRUSES:
        s = (nat_j[nat_j.virus == v].set_index("date").sort_index()[["ww_level", "ed_pct"]]
             .asfreq("7D").interpolate(limit=2).dropna())
        for h in (1, 2, 3):
            res = {}
            for with_ww in (False, True):
                X, target, ly = ed_design(s, h, with_ww)
                ok = X.notna().all(axis=1) & target.notna()
                idx = X.index[ok]
                errs = []
                for i in range(len(idx) - BACKTEST_WEEKS, len(idx)):
                    if i < 52:
                        continue
                    tr = idx[:i - h + 1]            # targets fully observed by week idx[i]
                    m = sm.OLS(target[tr], X.loc[tr]).fit()
                    pred = float(m.predict(X.loc[[idx[i]]]).iloc[0])
                    actual = float(target[idx[i]])
                    # absolute % error on the ED share itself
                    errs.append(abs(np.exp(pred - actual) - 1))
                res[with_ww] = np.mean(errs) * 100 if errs else np.nan
            rows.append({"virus": v, "horizon_weeks": h, "mape_ed_only": res[False],
                         "mape_with_ww": res[True],
                         "improvement_pct": (1 - res[True] / res[False]) * 100})
            # forecast from the latest week with the wastewater model
            X, target, ly = ed_design(s, h, True)
            ok = X.notna().all(axis=1) & target.notna()
            m = sm.OLS(target[ok], X[ok]).fit()
            resid = m.resid
            last = X.dropna().index.max()
            pred = float(m.predict(X.loc[[last]]).iloc[0])
            fc_rows.append({"virus": v, "date": last + pd.Timedelta(weeks=h),
                            "ed_pct": float(np.exp(ly[last] + pred)),
                            "lo80": float(np.exp(ly[last] + pred + resid.quantile(0.1))),
                            "hi80": float(np.exp(ly[last] + pred + resid.quantile(0.9)))})
    return pd.DataFrame(rows), pd.DataFrame(fc_rows)


# ---------- summary ----------

def kpis(nat_j, nat, ww_fc):
    out = {}
    for v in VIRUSES:
        s = nat[nat.virus == v].sort_values("date")
        last = s.iloc[-1]
        prev = s[s.date <= last.date - pd.Timedelta(weeks=2)].iloc[-1]
        since = s[s.date >= "2022-10-01"]["ww_level"]
        f = ww_fc[ww_fc.virus == v].iloc[-1]
        e = nat_j[(nat_j.virus == v)].dropna(subset=["ed_pct"]).sort_values("date").iloc[-1]
        out[v] = {"week": last.date.strftime("%Y-%m-%d"), "ww_level": round(float(last.ww_level), 2),
                  "change_2wk": round(float(last.ww_level - prev.ww_level), 2),
                  "pctile": round(float((since < last.ww_level).mean() * 100)),
                  "n_sites": int(last.n_sites),
                  "fc_level": round(float(f.ww_level), 2), "fc_date": f.date.strftime("%Y-%m-%d"),
                  "ed_week": e.date.strftime("%Y-%m-%d"), "ed_pct": round(float(e.ed_pct), 2)}
    return out


def run(site_weeks, nat, states, ed):
    nat_j = join(nat, ed[ed.state == "US"].drop(columns="state"))
    st_j = join(states, ed[ed.state != "US"])
    start = pd.Timestamp("2022-01-01")
    nat_j = nat_j[nat_j.date >= start].sort_values(["virus", "date"])
    st_j = st_j[st_j.date >= start].sort_values(["virus", "state", "date"])

    lag_nat, lag_st = lag_tables(nat_j, st_j)
    waves = wave_table(nat_j)
    ww_fc, ww_bt, orders = ww_forecast(nat)
    ed_bt, ed_fc = ed_backtest(nat_j)

    lag_summary = {}
    for v in VIRUSES:
        c = lag_nat[lag_nat.virus == v].set_index("lag_weeks")["corr"]
        g = lag_st[lag_st.virus == v]
        w = waves[(waves.virus == v)].dropna(subset=["lead_days"])
        lag_summary[v] = {"best_lag_weeks": int(c.idxmax()), "best_corr": round(float(c.max()), 2),
                          "corr_lag0": round(float(c.get(0)), 2),
                          "states": int(len(g)),
                          "states_ww_first": int((g.best_lag_weeks > 0).sum()),
                          "states_same_week": int((g.best_lag_weeks == 0).sum()),
                          "states_median_lag": float(g.best_lag_weeks.median()) if len(g) else None,
                          "waves": int(len(w)), "median_peak_lead_days": float(w.lead_days.median()) if len(w) else None}

    meta = {
        "built": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "ww_through": nat.date.max().strftime("%Y-%m-%d"),
        "ed_through": ed.date.max().strftime("%Y-%m-%d"),
        "sites": {v: int(site_weeks[site_weeks.virus == v].site.nunique()) for v in VIRUSES},
        "site_weeks": int(len(site_weeks)),
        "states": {v: int(states[states.virus == v].state.nunique()) for v in VIRUSES},
        "arima_orders": {v: list(o) for v, o in orders.items()},
        "lag": lag_summary,
        "kpi": kpis(nat_j, nat, ww_fc),
    }
    keep_states = st_j[st_j.date >= "2022-10-01"]
    return {
        "national": nat_j, "states": keep_states, "lag_national": lag_nat, "lag_states": lag_st,
        "waves": waves, "ww_forecast": ww_fc, "ww_backtest": ww_bt,
        "ed_backtest": ed_bt, "ed_forecast": ed_fc, "meta": meta,
    }
