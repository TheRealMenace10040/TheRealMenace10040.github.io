"""Build the Chicago food inspections database and the dashboard data.

Steps:
  1. Download the inspections CSV and community area boundaries from the
     City of Chicago data portal (skipped if the files are already there).
  2. Load the CSV into DuckDB and tag each address with its community area
     (point-in-polygon with shapely).
  3. Run sql/01_clean.sql and sql/02_analysis.sql.
  4. Export the analysis tables to data/*.csv and data/dashboard.json.

Usage:  python src/build.py            (from projects/chicago-food-inspections/)
Needs:  pip install duckdb shapely
"""
import json
import urllib.request
from pathlib import Path

import duckdb
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"            # not committed: the CSV is ~350 MB
DATA = ROOT / "data"
SQL = ROOT / "sql"

INSPECTIONS_URL = "https://data.cityofchicago.org/api/views/4ijn-s7e5/rows.csv?accessType=DOWNLOAD"
AREAS_URL = "https://data.cityofchicago.org/api/geospatial/igwz-8jzy?method=export&format=GeoJSON"


def download(url, path):
    if path.exists():
        print(f"using cached {path.name}")
        return
    print(f"downloading {path.name} ...")
    path.parent.mkdir(exist_ok=True)
    urllib.request.urlretrieve(url, path)


def community_area_lookup(con, areas_geojson):
    """Map every distinct latitude/longitude in the data to one of Chicago's 77 community areas."""
    features = json.loads(areas_geojson.read_text())["features"]
    polys = [shape(f["geometry"]) for f in features]
    names = [(int(f["properties"]["area_numbe"]), f["properties"]["community"].title()) for f in features]
    tree = STRtree(polys)

    points = con.sql("""
        SELECT DISTINCT TRY_CAST(Latitude AS DOUBLE) lat, TRY_CAST(Longitude AS DOUBLE) lon
        FROM raw WHERE Latitude IS NOT NULL
    """).fetchall()
    rows = []
    for lat, lon in points:
        hits = tree.query(Point(lon, lat), predicate="within")
        if len(hits):
            rows.append((lat, lon, *names[hits[0]]))
    con.execute("CREATE OR REPLACE TABLE loc_area (latitude DOUBLE, longitude DOUBLE, community_area_no INT, community_area VARCHAR)")
    con.executemany("INSERT INTO loc_area VALUES (?, ?, ?, ?)", rows)
    print(f"{len(rows):,} of {len(points):,} locations fall inside a community area")
    return features


def area_shapes(features):
    """Simplified outlines of the 77 areas, projected to SVG coordinates for the dashboard map."""
    import math
    lat0 = math.radians(41.84)
    out, xs, ys = [], [], []
    for f in features:
        g = shape(f["geometry"]).simplify(0.0008, preserve_topology=True)
        polys = g.geoms if g.geom_type == "MultiPolygon" else [g]
        rings = [[(lon * math.cos(lat0), -lat) for lon, lat in p.exterior.coords] for p in polys]
        for r in rings:
            xs += [x for x, _ in r]; ys += [y for _, y in r]
        out.append((int(f["properties"]["area_numbe"]), rings))
    minx, miny = min(xs), min(ys)
    scale = 600 / (max(ys) - miny)          # map is 600 units tall
    shapes = {}
    for no, rings in out:
        d = "".join("M" + "L".join(f"{(x - minx) * scale:.1f},{(y - miny) * scale:.1f}" for x, y in r) + "Z" for r in rings)
        shapes[no] = d
    width = round((max(xs) - minx) * scale, 1)
    return {"width": width, "height": 600, "paths": shapes}


def main():
    download(INSPECTIONS_URL, RAW / "food_inspections.csv")
    download(AREAS_URL, RAW / "community_areas.geojson")

    con = duckdb.connect(str(RAW / "food_inspections.duckdb"))
    con.execute(f"""
        CREATE OR REPLACE TABLE raw AS
        SELECT * FROM read_csv('{RAW / "food_inspections.csv"}', all_varchar = true, header = true)
    """)
    features = community_area_lookup(con, RAW / "community_areas.geojson")

    con.execute((SQL / "01_clean.sql").read_text())
    con.execute((SQL / "02_analysis.sql").read_text())

    DATA.mkdir(exist_ok=True)
    tables = [t for (t,) in con.sql("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'out_%' ORDER BY 1").fetchall()]
    dash = {}
    for t in tables:
        rel = con.table(t)
        rel.write_csv(str(DATA / f"{t[4:]}.csv"))
        cols = rel.columns
        dash[t[4:]] = [dict(zip(cols, r)) for r in rel.fetchall()]
        print(f"{t[4:]:<22} {len(dash[t[4:]]):>6} rows")
    dash["map"] = area_shapes(features)
    dash["built"] = con.sql("SELECT strftime(MAX(inspection_date), '%Y-%m-%d') FROM inspections").fetchone()[0]

    (DATA / "dashboard.json").write_text(json.dumps(dash, default=str, separators=(",", ":")))
    print(f"dashboard.json: {(DATA / 'dashboard.json').stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
