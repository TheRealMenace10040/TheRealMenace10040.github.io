# Cleanroom Environmental Monitoring Dashboard

**Live dashboard:** https://therealmenace10040.github.io/projects/cleanroom-em-dashboard/

An interactive environmental monitoring (EM) and CAPA dashboard for a medical device manufacturing site. It shows one year of results for 17 cleanrooms and gowning rooms, set up the way a QC microbiology lab actually tests them.

All data is simulated. No real site data is used.

## What it shows

| Section | What you can do with it |
|---|---|
| Summary | Rooms monitored, pass rate, open CAPAs and mean time to close, for whatever is filtered |
| Trend | Monthly mean for any test, plotted against alert and action limits. Action results are marked individually |
| Root cause Pareto | Alert and Action causes ranked, with the cumulative % and the 80% cut-off |
| Facility matrix | Worst result per room per month. Click a room to filter the whole page |
| Audit log | Every result with sample count, limits, CAPA number and status, root cause, analyst and QA reviewer |

Filters: suite or room, test type, result (Pass / Alert / Action) and free-text search.

## How the data is modelled

- **Rooms:** 7 production cleanrooms (two ISO 5, one ISO 6, two ISO 7, two ISO 8) and 10 ISO 8 gowning rooms. The ISO 5 and ISO 6 rooms have two-stage gowning (pre-gown and final gown); the others have one.
- **Tests and cadence:**
  - Production rooms: air microbial (AM), air particulate (AP), personnel (PER), work surface (WS) and differential pressure (DP), monthly.
  - Gowning rooms: AM, AP and DP, quarterly.
- **Units:** AM in CFU/m³, AP as particles/m³ at 0.5 µm and 5.0 µm, PER and WS in CFU/plate, DP in inches of water column.
- **Averaging:** each result is the mean of 12 to 40 samples (AM, AP, PER, WS) or 1 to 4 entrance readings (DP), and the sample count is shown with every record.
- **Limits:**
  - Particulates use ISO 14644-1 class limits.
  - Microbial action levels are illustrative and modelled on EU GMP Annex 1, with alert at 60% of action.
  - DP is pass/fail against a floor: below 0.030 in. WC is an Alert and below 0.020 in. WC is an Action.
- **Window:** Sep 2025 to Aug 2026, 540 test events.
- **CAPA:** every Action result opens a CAPA. Closed CAPAs record days to close, and that drives the mean time to close.

The data comes from a seeded random generator, so it's the same every time the page loads. A few events are scripted so the year has something to investigate, including a HEPA filter problem in the Gamma buffer suite and a pressure failure in Delta followed by a gowning breach.

## Findings from the simulated year

- 55 of 540 test events (10.2%) hit alert or action levels, and 18 of those were actions.
- The Gamma ISO 6 buffer suite stayed at alert or action every month from October to April, then held clean from May on.
- HEPA filter saturation is the most common root cause (10 of 55). 7 of 13 causes account for 80% of excursions.

## Built with

HTML, CSS and JavaScript in a single file, with [Chart.js](https://www.chartjs.org/) for the trend chart. The Pareto and facility matrix are plain HTML tables. There's no build step: open `index.html` in a browser.
