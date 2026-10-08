"""Build the wastewater virus tracker data.

Steps:
  1. Download CDC wastewater data (NWSS) for SARS-CoV-2, influenza A and RSV
     from data.cdc.gov, and CDC's weekly emergency department (ED) visit
     shares from the CDC forecast hubs on GitHub (skipped if already in raw/).
  2. Turn every sewershed's concentrations into a weekly site level, then take
     the median across sites for the nation and each state (src/levels.py).
  3. Answer the three questions (src/analysis.py):
       - does wastewater move before ED visits?
       - how do seasonal peaks compare year to year?
       - can a simple model forecast the next few weeks?
  4. Write data/*.csv and data/dashboard.json, which index.html reads.

Usage:  python src/build.py            (from projects/wastewater-tracker/)
Needs:  pip install pandas pyarrow statsmodels
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analysis  # noqa: E402
import levels    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"      # not committed: the wastewater files are a few hundred MB
DATA = ROOT / "data"

CDC = "https://data.cdc.gov"
# NWSS sample-level datasets, one per virus. Each row is one sample from one sewershed.
WASTEWATER = {
    "covid": {"id": "j9g8-acpt", "targets": ["sars-cov-2"]},
    "flu":   {"id": "ymmh-divb", "targets": ["fluav"]},
    "rsv":   {"id": "45cq-cw4i", "targets": ["rsv"]},
}
# Column names differ a little between NWSS releases, so take the first one present.
COLUMNS = {
    "site":   ["sewershed_id", "key_plot_id", "wwtp_id"],
    "state":  ["wwtp_jurisdiction", "reporting_jurisdiction", "state"],
    "date":   ["sample_collect_date", "date"],
    "target": ["pcr_target"],
    "conc":   ["pcr_target_flowpop_lin", "pcr_target_avg_conc", "pcr_conc_lin"],
    "pop":    ["population_served"],
}

HUB = "https://raw.githubusercontent.com"
ED = {
    "covid": f"{HUB}/CDCgov/covid19-forecast-hub/main/target-data/time-series.parquet",
    "rsv":   f"{HUB}/CDCgov/rsv-forecast-hub/main/target-data/time-series.parquet",
    "flu":   f"{HUB}/cdcepi/FluSight-forecast-hub/main/target-data/target-ed-visits-prop.csv",
}
LOCATIONS = f"{HUB}/cdcepi/FluSight-forecast-hub/main/auxiliary-data/locations.csv"


def download(url, path):
    if path.exists():
        print(f"using cached {path.name}")
        return
    print(f"downloading {path.name} ...")
    path.parent.mkdir(exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "portfolio-build"})
    with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def dataset_columns(dataset_id):
    with urllib.request.urlopen(f"{CDC}/api/views/{dataset_id}.json", timeout=60) as r:
        meta = json.load(r)
    return [c["fieldName"] for c in meta["columns"]], meta.get("name", dataset_id)


def download_wastewater(virus, spec):
    """Page through the Socrata API, keeping only the columns the analysis needs."""
    path = RAW / f"ww_{virus}.csv"
    if path.exists():
        print(f"using cached {path.name}")
        return path
    available, name = dataset_columns(spec["id"])
    pick = {}
    for key, options in COLUMNS.items():
        found = [c for c in options if c in available]
        if found:
            pick[key] = found[0]
    missing = {"site", "state", "date", "conc"} - pick.keys()
    if missing:
        raise SystemExit(f"{name} ({spec['id']}) has no column for {missing}. Columns: {available}")
    print(f"{virus}: {name} ({spec['id']}) -> {pick}")

    select = ",".join(f"{col} AS {key}" for key, col in pick.items())
    where = f"{pick['conc']} IS NOT NULL"
    if "target" in pick:
        where += " AND " + pick["target"] + " IN (" + ",".join(f"'{t}'" for t in spec["targets"]) + ")"
    RAW.mkdir(exist_ok=True)
    tmp = path.with_suffix(".part")
    offset, page, header = 0, 200_000, True
    with open(tmp, "wb") as out:
        while True:
            q = urllib.parse.urlencode({"$select": select, "$where": where, "$order": ":id",
                                        "$limit": page, "$offset": offset})
            with urllib.request.urlopen(f"{CDC}/resource/{spec['id']}.csv?{q}", timeout=600) as r:
                lines = r.read().splitlines(keepends=True)
            rows = lines[1:]
            out.write(b"".join(lines if header else rows))
            header = False
            offset += len(rows)
            print(f"  {offset:,} rows")
            if len(rows) < page:
                break
    tmp.rename(path)
    return path


def load_ed():
    """Weekly share of ED visits for each virus, by state and nationally (NSSP via the CDC hubs)."""
    frames = []
    for virus, url in ED.items():
        path = RAW / f"ed_{virus}{Path(url).suffix}"
        download(url, path)
        if path.suffix == ".parquet":
            d = pd.read_parquet(path)
            d = d[d["target"].str.contains("prop ed visits")]
            d = d[d["as_of"] == d["as_of"].max()]          # latest version of each week
            d = d.rename(columns={"target_end_date": "date", "observation": "value"})
        else:
            d = pd.read_csv(path, dtype={"location": str})
        d = d[["date", "location", "value"]].assign(virus=virus)
        frames.append(d)
    ed = pd.concat(frames)
    ed["date"] = pd.to_datetime(ed["date"])
    ed["value"] = ed["value"] * 100                       # proportion -> percent of all ED visits
    download(LOCATIONS, RAW / "locations.csv")
    loc = pd.read_csv(RAW / "locations.csv", dtype={"location": str})
    ed = ed.merge(loc[["location", "abbreviation", "location_name"]], on="location", how="left")
    ed["state"] = ed["abbreviation"].where(ed["location"] != "US", "US")
    return ed[["virus", "state", "date", "value"]].dropna().sort_values(["virus", "state", "date"])


def state_lookup():
    download(LOCATIONS, RAW / "locations.csv")
    loc = pd.read_csv(RAW / "locations.csv", dtype={"location": str})
    loc = loc[loc["location"] != "US"]
    lookup = dict(zip(loc["abbreviation"], loc["abbreviation"]))
    lookup.update(zip(loc["location_name"], loc["abbreviation"]))
    lookup.update(zip(loc["location_name"].str.upper(), loc["abbreviation"]))
    return lookup


def main():
    states = state_lookup()
    ww_raw = {v: levels.read_samples(download_wastewater(v, s), v, states) for v, s in WASTEWATER.items()}
    ww = pd.concat(ww_raw.values())
    site_weeks = levels.site_weeks(ww)
    nat, states = levels.aggregate(site_weeks)
    ed = load_ed()

    out = analysis.run(site_weeks, nat, states, ed)
    export(out, DATA)


def compact_states(t):
    """{virus: {state: {ww: [...], ed: [...]}}} on one shared weekly date axis, to keep the JSON small."""
    dates = pd.date_range(t["date"].min(), t["date"].max(), freq="7D")
    series = {}
    for (v, st), g in t.groupby(["virus", "state"]):
        g = g.set_index("date").reindex(dates)
        series.setdefault(v, {})[st] = {
            k: [None if pd.isna(x) else round(float(x), 3) for x in g[col]]
            for k, col in (("ww", "ww_level"), ("ed", "ed_pct"))}
    return {"dates": [d.strftime("%Y-%m-%d") for d in dates], "series": series}


def export(out, data_dir):
    data_dir.mkdir(exist_ok=True)
    dash = {}
    for name, table in out.items():
        if isinstance(table, pd.DataFrame):
            table.to_csv(data_dir / f"{name}.csv", index=False)
            if name == "states":
                dash[name] = compact_states(table)
                continue
            t = table.copy()
            for c in t.columns:
                if pd.api.types.is_datetime64_any_dtype(t[c]):
                    t[c] = t[c].dt.strftime("%Y-%m-%d")
            dash[name] = json.loads(t.to_json(orient="records", double_precision=4))
            print(f"{name:<18} {len(t):>6} rows")
        else:
            dash[name] = table
    (data_dir / "dashboard.json").write_text(json.dumps(dash, separators=(",", ":")))
    print(f"dashboard.json: {(data_dir / 'dashboard.json').stat().st_size / 1024:.0f} KB")

if __name__ == "__main__":
    main()
