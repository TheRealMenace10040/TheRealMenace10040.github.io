"""Build the Olist customer retention database and the dashboard data.

Steps:
  1. Download the 8 Olist CSVs from Olist's own GitHub repo
     (github.com/olist/work-at-olist-data, MIT licence). Skipped if already in raw/.
  2. Load them into DuckDB as raw_* tables.
  3. Run sql/01_model.sql and sql/02_analysis.sql.
  4. Test whether the repeat-rate gaps are bigger than chance (two-proportion z-test).
  5. Export the analysis tables to data/*.csv and data/dashboard.json.

Usage:  python src/build.py            (from projects/olist-customer-retention/)
Needs:  pip install duckdb
"""
import json
import math
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"            # not committed: ~125 MB of CSVs
DATA = ROOT / "data"
SQL = ROOT / "sql"

BASE_URL = "https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/"
TABLES = {
    "orders": "olist_orders_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}
EXPORTS = ["kpis", "monthly", "cohort", "late_vs_review", "late_by_state", "late_by_route",
           "repeat_by_first", "repeat_by_category", "return_gap", "rfm", "categories"]


def download():
    RAW.mkdir(exist_ok=True)
    for name in TABLES.values():
        path = RAW / name
        if path.exists():
            print(f"using cached {name}")
            continue
        print(f"downloading {name} ...")
        urllib.request.urlretrieve(BASE_URL + name, path)


def load(con):
    for table, name in TABLES.items():
        con.execute(f"CREATE OR REPLACE TABLE raw_{table} AS "
                    f"SELECT * FROM read_csv('{(RAW / name).as_posix()}', header = true)")
        n = con.sql(f"SELECT COUNT(*) FROM raw_{table}").fetchone()[0]
        print(f"raw_{table}: {n:,} rows")


def two_prop_z(x1, n1, x2, n2):
    """Two-sided two-proportion z-test. Returns (difference in points, z, p)."""
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se
    return round((p1 - p2) * 100, 2), round(z, 2), round(math.erfc(abs(z) / math.sqrt(2)), 4)


def significance(con):
    """Compare the two ends of each first-experience factor."""
    rows = {(f, lvl): (b, r) for f, lvl, b, r in
            con.sql("SELECT factor, level, buyers, returned FROM repeat_by_first").fetchall()}
    pairs = [("Delivery", "On time", "Late"),
             ("Review", "4 or 5 stars", "1 or 2 stars"),
             ("Route", "Same state", "Interstate"),
             ("First order value", "Quintile 5", "Quintile 1")]
    out = []
    for factor, a, b in pairs:
        (na, xa), (nb, xb) = rows[(factor, a)], rows[(factor, b)]
        diff, z, p = two_prop_z(xa, na, xb, nb)
        out.append({"factor": factor, "a": a, "b": b, "diff_points": diff, "z": z, "p": p})
        print(f"{factor}: {a} vs {b}: {diff:+.2f} pts, z={z}, p={p}")

    cats = con.sql("SELECT category, buyers, returned FROM repeat_by_category ORDER BY repeat_rate DESC").fetchall()
    (top, nt, xt), (bot, nb, xb) = cats[0], cats[-1]
    diff, z, p = two_prop_z(xt, nt, xb, nb)
    out.append({"factor": "Category", "a": top, "b": bot, "diff_points": diff, "z": z, "p": p})
    print(f"Category: {top} vs {bot}: {diff:+.2f} pts, z={z}, p={p}")
    return out


def records(con, table):
    cur = con.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]

    def clean(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()[:10]
        if isinstance(v, Decimal):
            return float(v)
        return v
    return [{c: clean(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def main():
    download()
    con = duckdb.connect()
    load(con)
    for f in sorted(SQL.glob("*.sql")):
        print(f"running {f.name}")
        con.execute(f.read_text())

    tests = significance(con)

    DATA.mkdir(exist_ok=True)
    out = {}
    for t in EXPORTS:
        con.execute(f"COPY {t} TO '{(DATA / (t + '.csv')).as_posix()}' (HEADER)")
        out[t] = records(con, t)
    out["kpis"] = out["kpis"][0]
    out["tests"] = tests
    (DATA / "dashboard.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {len(EXPORTS)} CSVs and dashboard.json to {DATA}")
    print(json.dumps(out["kpis"], indent=2))


if __name__ == "__main__":
    main()
