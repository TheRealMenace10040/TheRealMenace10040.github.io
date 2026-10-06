# Lab Supply & Vendor Performance Tracker

An Excel tool for tracking time-sensitive lab supplies. It shows which vendors deliver late, which lots are about to expire, and what needs to be reordered. Repetitive steps are automated with VBA.

> **All data is synthetic.** Vendor names, items, prices and orders are randomly generated (seeded, reproducible).

## Problem
A QC microbiology lab runs on perishable materials. Culture media can have a 60-120 day shelf life, and biological indicators and reagents expire too. A late delivery or an expired lot can delay testing. Purchasing needs to know three things: what to reorder, from whom, and which vendors can't be trusted on lead time.

## What's inside
| Sheet | What it does | Key techniques |
|---|---|---|
| PurchaseOrders | 320 POs over 12 months; computes lead time, on-time flag, days late | INDEX/MATCH, IF logic, Excel Tables |
| Inventory | Lots on hand with days-to-expiry and Expired / Expiring / OK status | Date math, conditional formatting |
| ReorderAlerts | Usable (non-expired) stock + open POs vs. minimum; suggests reorder qty | SUMIFS with multiple criteria |
| VendorScorecard | Orders, spend, avg lead time vs. quoted, on-time %, Preferred / Monitor / At risk rating | COUNTIFS, AVERAGEIFS, SUMIFS |
| Dashboard | Headline KPIs, on-time % by vendor chart, monthly spend trend | Charts, linked KPIs |

## Automation (`vba/VendorTracker.bas`)
- **RefreshAll_And_Stamp**: recalculates everything, sorts the reorder list so urgent items come first, timestamps the dashboard and shows a summary pop-up.
- **ExportReorderList**: writes every flagged item to a dated CSV that purchasing can use directly.
- **ImportPOs**: appends new POs from a CSV export (try `sample_new_POs.csv`). It skips duplicate PO numbers and fills in the formula columns.

To use the macros, open the workbook, press Alt+F11, choose File > Import File, pick the `.bas` file, and save as `.xlsm`.

## Sample findings (as of 2026-10-01)
- Overall on-time delivery is **89.7%**, and average lead time is **10.5 days**.
- **Apex Calibration** is flagged *At risk*: 75% on time, averaging 21.5 days against 21 quoted.
- **Pacific BioReagents** and **BioIndicator Labs** are flagged *Monitor* (85% and 88%).
- **6 items** are below their reorder point, **5 lots** have expired and **2 lots** expire within 30 days.

## Rebuild
`python src/build_workbook.py` regenerates the workbook and sample CSV (needs `openpyxl`).
