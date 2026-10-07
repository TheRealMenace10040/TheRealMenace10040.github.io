# Deviation and CAPA Tracker

**Live dashboard:** https://therealmenace10040.github.io/projects/deviation-capa-tracker/

An interactive deviation and CAPA tracker for a medical device manufacturing site. It covers 18 months of deviations across valve assembly, packaging, sterilization, QC microbiology, warehouse and facilities, and answers the questions a QA review asks:
- What's open and how old is it?
- Are we closing deviations on time?
- Which problems keep coming back?
- Did our CAPAs work?

All data is simulated. No real site data is used.

**Excel version:** [Deviation_CAPA_Tracker.xlsx](Deviation_CAPA_Tracker.xlsx) (same records, built with live formulas)

## What it shows

| Section | What you can do with it |
|---|---|
| Summary | Open and overdue deviations, median days to close (last 90 days vs. the 6 months before), repeat rate, and CAPA effectiveness |
| Close-out trend | Deviations opened and closed per month, with the median days to close against the 30-day target |
| Aging | Open deviations by severity in 0–30, 31–60, 61–90 and 90+ day buckets, plus the oldest open record |
| Repeat root causes | Every equipment / root cause pair that recurred within 180 days, with its full history and CAPA status. CAPAs that failed their effectiveness check are listed first |
| Root cause Pareto | Root causes ranked, with % and cumulative % |
| Deviation register | Every record with severity, status, days open, CAPA and owner. Filter by status (open, overdue, closed), search, and download as CSV |

Filters for area, severity and root cause apply to the whole page. Search also matches CAPA effectiveness, so typing "ineffective" lists the deviations whose CAPAs failed.

## How the data is modelled

- **Volume:** 7 to 11 deviations a month from Apr 2025 to Sep 2026, 167 in total. The data date is 30 Sep 2026.
- **Severity:** about 72% Minor, 24% Major, 4% Critical.
- **Days to close:** lognormal, centred around 17 days for Minor and 24 for Major. From mid-May 2026 a simulated QA staffing gap adds 12 to 24 days to every close-out.
- **Closure target:** 30 days. An open record past 30 days is overdue.
- **CAPA:**
  - Raised for every Major and Critical deviation, and for any Minor that repeats.
  - Due 90 days after the deviation closes.
  - Effectiveness check 180 days after CAPA closure.
- **Repeat:** the same root cause on the same equipment or process within 180 days of the previous deviation.
- **Ineffective CAPA:** the same root cause comes back on the same equipment or process within 180 days of the CAPA closing.

The data comes from a seeded random generator, so it's the same every time the page loads. Background records are generated so that most CAPAs hold. A few records are scripted so the period has something to investigate:
- A line-clearance failure on packaging line PL-1 that keeps coming back.
- An incubator that keeps going out of calibration.
- A Critical sterilization deviation that has been stuck open.

## Findings from the simulated data

- **Close-out slowed down.** Monthly median days to close sat between 15 and 23 days through May 2026, then jumped to 35 to 37 days from June on. Deviations closed in the last 90 days took a median of 36 days, against 16 days in the 6 months before. 7 of the 13 open deviations are overdue.
- **One problem keeps coming back.** "Line clearance not performed" on packaging line PL-1 happened 4 times, the last one a Critical. Both CAPAs raised for it were closed and both failed: the first closed on 14 Dec 2025 and the line had the same deviation 37 days later. These are the only 2 failures among the 19 CAPAs that have been checked (89% effective).
- **The oldest open record is a Critical.** An EtO sterilizer malfunction has been open for 99 days.
- **Documentation errors are the biggest category.** GDP / documentation errors account for 22.8% of all deviations. Together with equipment malfunctions and procedures not followed, they make up just over half.

## Excel version

[`Deviation_CAPA_Tracker.xlsx`](Deviation_CAPA_Tracker.xlsx) holds the same 167 records as a working tracker you can keep adding to. Every calculated column and dashboard number is an Excel formula, so it updates as records are added, closed or re-dated.

| Sheet | What's on it |
|---|---|
| Instructions | How to add and close deviations and CAPAs, the colour key, definitions |
| Dashboard | Key figures, aging grid by severity, summary by area, monthly close-out table and chart, root-cause Pareto and chart |
| Settings | Data date, 30-day closure target, warning threshold, CAPA due days, repeat and effectiveness windows, and the drop-down lists |
| Deviation Log | Inputs in columns A to J (blue). Status, days open, overdue, aging bucket, repeat flag, CAPA due / status / effectiveness and the helper columns are formulas, filled down to row 400 |
| Repeat Analysis | Equipment / root-cause pairs that repeated, with counts, first and last dates, and CAPA results |

Features:
- Drop-downs for area, severity, root cause and owner, and date validation on the date columns.
- Overdue rows turn red and due-soon rows turn amber. "Ineffective" CAPAs are flagged in red.
- Change **Data as of** on the Settings sheet (or set it to `=TODAY()`) and every age, overdue flag and effectiveness result rolls forward.
- Formulas use `COUNTIFS`, `MEDIAN`, `MINIFS` / `MAXIFS`, `EOMONTH` and one array `MEDIAN(IF())` per month. No macros.

I checked all 167 rows of calculated columns against the web tracker's output, and they match exactly. The workbook is generated by [`excel/build_workbook.py`](excel/build_workbook.py) (openpyxl) from [`excel/deviations.json`](excel/deviations.json).

## Built with

Web: HTML, CSS and JavaScript in a single file, with [Chart.js](https://www.chartjs.org/) for the close-out trend. The aging grid, repeat analysis and Pareto are plain HTML tables. There's no build step: open `index.html` in a browser.

Excel: Python (openpyxl) writes the workbook; all the logic inside it is Excel formulas.
