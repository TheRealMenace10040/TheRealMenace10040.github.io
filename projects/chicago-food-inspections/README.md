# What Makes a Chicago Food Inspection Fail?

**Live dashboard:** https://therealmenace10040.github.io/projects/chicago-food-inspections/

A SQL analysis of every City of Chicago food inspection since July 2018 (120,670 scored inspections of 24,917 businesses), with an interactive dashboard. This is real public data from the [City of Chicago Data Portal](https://data.cityofchicago.org/Health-Human-Services/Food-Inspections/4ijn-s7e5). It is my own analysis, not an official city report.

## Questions

1. Which violations predict a failed inspection?
2. Do re-inspections pass, and does a fail predict the next routine inspection?
3. Which neighborhoods and facility types fail most?

## Findings

- **22.7%** of inspections failed (Jul 2018 to Oct 2026).
- **Pests are the strongest common signal.** Insects, rodents or animals were cited in 17% of inspections. 64% of those failed, against 14% without them (4.4x lift), and pests show up in 47% of all fails.
- **Unfixed problems are worse.** When a priority foundation violation from the last visit was still there, 89% of inspections failed.
- **Severity tags almost decide the result.** Inspections with only core violations (or none) failed 2.2% of the time. With both priority and priority foundation violations, 70% failed.
- **Re-inspections usually pass.** 84% of failed businesses passed at the next visit (median 7 days later) and 12% failed again.
- **But a fail still carries forward.** After a failed routine inspection, the next routine inspection fails 31% of the time, against 19% after a clean pass.
- **Location and type matter.** South Chicago and Auburn Gresham fail about 40% of first visits, O'Hare 13%. Bars and taverns fail most (32%), catering least (17%).

## What's in the dashboard

| Section | What it shows |
|---|---|
| Summary strip | Fail rate, businesses, re-inspection pass rate, median days to re-inspection |
| Fail rate by month | Monthly trend since Jul 2018, with inspection volume below |
| Violations | Top 15 violations ranked by lift, share of all fails, or how often cited |
| Severity / next routine inspection | Fail rate by severity mix, and by the previous routine result |
| Re-inspections | What happened at the next visit after a fail, and how many days later |
| Neighborhoods | Map of Chicago's 77 community areas shaded by fail rate, with the highest and lowest areas |
| Facility matrix | Fail rate for every facility type x inspection purpose |
| The SQL | The main queries, inline |

A facility-type filter updates the summary, trend, violations, severity, re-inspection and map sections.

## How it's built

1. `src/build.py` downloads the inspections CSV and the community area boundaries into `raw/` (not committed, about 350 MB).
2. It loads the CSV into DuckDB and tags each inspection with its community area (point-in-polygon with shapely).
3. It runs `sql/01_clean.sql`, then `sql/02_analysis.sql`.
4. It exports every `out_*` table to `data/*.csv` and `data/dashboard.json`, which `index.html` reads.


- **`sql/01_clean.sql`** types and standardizes columns, removes 225 duplicate inspections with `QUALIFY ROW_NUMBER()`, groups 472 free-text facility types into 11, groups inspection types by purpose, and splits the violations text field into one row per violation.
- **`sql/02_analysis.sql`** answers the questions. It uses CTEs, `LEAD()` / `LAG()` window functions over each business's history, `GROUPING SETS` for per-group and overall numbers in one pass, `RANK()`, `MEDIAN()` and `FILTER` clauses.
- **`index.html`** is a single file (HTML, CSS, JavaScript and Chart.js) that reads `data/dashboard.json`.

To rebuild:

```
pip install duckdb shapely
python src/build.py
python -m http.server     # then open http://localhost:8000
```

## Method notes

- **Scope:** from 1 Jul 2018, when Chicago adopted the FDA Food Code and renumbered every violation. Older inspections use a different checklist.
- **Fail rate** = Fail / (Pass + Pass w/ Conditions + Fail). Out of Business, No Entry and Not Ready visits are left out.
- **Re-inspection** = the same license's next visit within 120 days of a fail (97.6% of those visits are logged as re-inspections). Fails from the last 120 days of data are excluded.
- **Checked:** the pest numbers were recomputed straight from the raw violation text and matched; facility groups add up to the overall total; re-inspection outcome shares sum to 100% for every group; the partial current month is left off the trend chart.
- **Neighborhood** rates use first visits only, so areas with many re-inspections don't look better than they are. Areas with fewer than 100 inspections aren't ranked.
- **Severity tags** come from the inspector's free-text comment, so they're only as complete as the comments.
- Lift shows which violations travel with a fail. It isn't cause and effect, and city rules fail some violations automatically.

## Built with

DuckDB (SQL), Python (shapely for the geography), JavaScript and Chart.js.
