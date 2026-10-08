# SPC Control Charts for QC Lab Test Results

**Live dashboard:** https://therealmenace10040.github.io/projects/spc-control-charts/

X-bar and R control charts for three routine QC lab tests, with Nelson rule flags, process capability (Cp / Cpk) and an out-of-control signal log. The aim is to show what SPC catches that a plain pass/fail review misses.

All data is simulated. No real site data is used.

## The three tests

| Test | Subgroup | What goes wrong | Which chart catches it |
|---|---|---|---|
| Growth promotion recovery, TSA media | 5 plates per media lot | The supplier changes a raw material, so recovery drops by about 7 points | X-bar: a sustained shift |
| WFI conductivity | 4 points of use per day | The polisher resin slowly wears out and conductivity drifts upward | X-bar: a trend |
| Autoclave exposure temperature | 4 load thermocouples per cycle | A blocked steam trap creates a cold spot at one probe for a week | R chart only: the spread opens up while the mean barely moves |

## What you can do with it

| Section | What it shows |
|---|---|
| Summary | Out-of-control points, first signal, and Cpk for the baseline vs. monitoring phases |
| X-bar chart | Subgroup means against the centre line, ±3σ limits and the ±1σ / ±2σ zones. Violations are marked in red |
| R chart | Subgroup ranges against R̄ and the upper control limit |
| Signal log | One row per flagged subgroup, with the rules it broke and the investigation outcome |
| Process capability | Cp and Cpk before and after the special cause, plus a histogram against the spec limits |
| Subgroup data | Every replicate result, downloadable as CSV |

Controls:
- **Test parameter:** switch between the three tests.
- **Control limits from:** limits from the first 20 subgroups (Phase I baseline, the default) or from all 40.
- **Nelson rules:** turn individual rules on or off.

## Method

- **Limits:** standard Shewhart constants. X-bar limits = X̿ ± A₂R̄; R limits = D₃R̄ and D₄R̄. Within-subgroup σ = R̄ / d₂.
- **Phase I / Phase II:** limits are set from subgroups 1 to 20 and then held fixed while subgroups 21 to 40 are monitored. Switch to "All subgroups" to see why this matters: on the autoclave, recalculating the limits with the bad week included widens them, and the flagged subgroups drop from 6 to 2.
- **Nelson rules on X-bar:**
  - 1: one point beyond 3σ
  - 2: nine in a row on one side of the centre line
  - 3: six in a row steadily rising or falling
  - 5: two of three beyond 2σ on the same side
  - 6: four of five beyond 1σ on the same side
- **R chart:** rule 1 only.
- **Spec limits (illustrative):**
  - WFI conductivity: USP <645> Stage 1, 1.3 µS/cm at 25 °C
  - Growth promotion: 70 to 130% recovery
  - Autoclave: 121.0 to 124.0 °C
- **Data:** 40 working-day subgroups, 1 Jun to 24 Jul 2026, from a seeded random generator, so the page is the same every time it loads. Each test has one scripted special cause in the monitoring phase. The baseline was checked to have no rule violations.

## Findings from the simulated data

- **Growth promotion:** the X-bar chart flags every lot from subgroup 29 on, one lot after the supplier change. No single plate ever fails the 70% limit, but Cpk falls from 1.52 to 1.26, below the usual 1.33 target.
- **WFI conductivity:** the drift starts at subgroup 24 and is flagged at subgroup 25. The highest single reading is 0.81 µS/cm, well under the 1.3 limit, so a pass/fail review would never have raised it.
- **Autoclave:** the X-bar chart shows nothing unusual. The R chart flags all six affected cycles (subgroups 30 to 35), Cpk drops from 1.37 to 0.76, and two probe readings fall below 121 °C.

## Built with

HTML, CSS and JavaScript in a single file, with [Chart.js](https://www.chartjs.org/) for the charts. The control limits, Nelson rules and capability calculations are written in plain JavaScript, with no stats library. There's no build step: open `index.html` in a browser.
