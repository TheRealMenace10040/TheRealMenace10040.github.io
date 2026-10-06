# Environmental Monitoring QC Trend Report

A small data pipeline for cleanroom environmental monitoring (EM) results. Python generates the data, SQL analyzes it, and a formula-driven Excel report presents it. A VBA macro builds the weekly report and exports it as a PDF.

> **All data is synthetic**, and the alert/action limits are illustrative only. They're not taken from any real SOP or company.

## Problem
QC labs sample cleanroom air, surfaces, compressed air and gloves every day. Someone has to compare each result to its alert and action limits, spot rooms that are trending worse, catch repeat excursions, and send a weekly summary. Doing that by hand is slow and easy to get wrong.

## Pipeline
1. **Python** (`src/build_report.py`) generates about 3,600 results across 5 rooms and 4 sample types for January-September 2026, including a realistic summer bump.
2. **SQL** (`sql/schema.sql`, `sql/analysis_queries.sql`) loads the results into SQLite and runs:
   - a view that classifies every result as Pass, Alert or Action
   - the monthly excursion rate by room
   - rooms whose last-30-day excursion rate is above their prior 90-day baseline (CTEs)
   - repeat excursions: the same room and sample type over a limit 3+ times in 14 days (self-join)
3. **Excel** (`EM_QC_Trend_Report.xlsx`):
   - `RawData` looks up the limits and flags each result.
   - `MonthlySummary` is a COUNTIFS matrix with a line chart and a bar chart.
   - The SQL outputs land on their own sheets.
   - Editing `Limits` makes everything recalculate.

## Automation (`vba/EMReport.bas`)
**BuildWeeklyReport** does the following:
- asks for a week-ending date and pulls that week's results
- lists every excursion, highlighting Alert results in yellow and Action results in red
- totals samples, alerts, actions and excursion % by room
- exports a landscape PDF

## Sample findings
- The overall excursion rate runs 2-5% per month most of the year, then jumps to **8.0% in July** and 6.0% in August.
- **CR-101** has risen from 1.2% to 3.4% over the last 30 days, compared with its 90-day baseline.
- **22 repeat-excursion events** were flagged for follow-up investigation.

## Rebuild
`python src/build_report.py` regenerates the data, SQL outputs and workbook (needs `openpyxl`).
