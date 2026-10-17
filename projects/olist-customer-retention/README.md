# E-commerce Customer Retention (Olist)

**Live dashboard:** https://therealmenace10040.github.io/projects/olist-customer-retention/

A SQL case study on 96,203 real orders from Olist, a Brazilian marketplace that lists small shops' products on big retail sites. The data covers Jan 2017 to Aug 2018.

The business question: **is Olist keeping its customers, and if not, is it the delivery experience that drives them away?**

## Bottom line

1. **Olist is a one-purchase business.** Only 2.0% of first-time buyers order again within 180 days (1,101 of 55,647), and 97.0% of revenue comes from first orders.
2. **Late deliveries wreck reviews, but they don't explain the churn.** 66% of late first orders get a 1 or 2 star review, against 9.5% of on-time ones. But late buyers come back at 1.6% vs 2.0%, and that gap isn't statistically significant (p = 0.10). Almost nobody comes back, happy or not.
3. **What you buy first matters more than how it went.** First orders in bags and accessories lead to a second order 3.1x as often as gadgets and gifts (3.2% vs 1.0%, p < 0.001). 55% of returns happen within 90 days.

**Recommendation:** fix delivery for the sake of ratings, and run retention as its own program.
- Pad promised dates on interstate routes to the northeast and in peak months.
- Send a second-order offer in the first 30 to 90 days. Start with repeat-prone categories and the 7,030 high-value one-time buyers who are still recent enough to win back.
- Each point of 180-day return rate is worth about R$115k a year at current volume (about 1% of revenue). That's worth doing, but acquisition will still drive growth.

## Findings

| # | Question | Answer |
|---|---|---|
| 1 | How many buyers come back? | 2.0% within 180 days. A naive count says 3.0%, but 28% of those "repeats" are one basket split into two checkouts on the same day. |
| 2 | How do cohorts hold up? | The average monthly cohort keeps 0.48% of buyers in month 1 and 0.25% in month 3. No cohort-month reaches 1%. |
| 3 | What does a late delivery do to reviews? | Bad reviews (1 or 2 stars) go from 9% on time to 32% at 1 to 3 days late, 68% at 4 to 7 days, and about 80% beyond a week. |
| 4 | When and where are deliveries late? | 6.8% overall. It spiked to 12.4% in Nov 2017 (Black Friday) and 19.0% in Mar 2018. Interstate orders are late 8.1% of the time vs 4.5% within a state. Alagoas is worst at 21.5%. The far north takes 25+ days but is rarely late, because its promised dates are already long. |
| 5 | What predicts a second order? | Delivery, review, route and order value each move the return rate by under half a point, and none passes a Bonferroni-corrected test (p < 0.01). First-order category does: 3.2% for bags and accessories vs 1.0% for gadgets. |
| 6 | When do returners come back? | 30% within 30 days, 55% within 90 days. |
| 7 | Who are the customers (RFM)? | High-value one-time buyers (top 20% of spend) are 19% of customers and 50% of revenue. |

## How it works

```
raw/ (8 CSVs, not committed)
  └─ src/build.py ── loads into DuckDB
       ├─ sql/01_model.sql     clean model: order_fact, delivered, customer_orders, first_orders
       ├─ sql/02_analysis.sql  11 analysis tables (kpis, monthly, cohort, late_vs_review, ... rfm)
       ├─ z-tests on repeat-rate gaps (Python, no extra libraries)
       └─ data/*.csv + data/dashboard.json  ──>  index.html (Chart.js)
```

SQL techniques used: multi-table joins across 7 tables, CTEs, window functions (`ROW_NUMBER`, `FIRST_VALUE`, `NTILE`, `PERCENT_RANK`, `SUM() OVER ()`), `QUALIFY`, `FILTER` clauses, date math for cohort offsets, and conditional aggregation.

### Data decisions

- **Buyer identity.** `customer_id` is new on every order. The person is `customer_unique_id`. If you count by `customer_id`, the repeat rate comes out as exactly 0%.
- **What counts as a return.** An order on a later calendar day than the first. Same-day second orders are left out, because most are a basket split into two checkouts.
- **Fair follow-up window.** Only buyers whose first order was at least 180 days before the data ends count toward the return rate. Otherwise recent buyers would be scored as lost just because time ran out.
- **Scope.** Delivered orders bought Jan 2017 to Aug 2018. Before 2017 the marketplace had only a few hundred orders, and after Aug 2018 the export is cut off.
- **Late.** Delivered after the estimated delivery date shown at checkout, compared by calendar day.
- **Duplicate reviews.** Some orders have more than one review. The latest answered one is kept.
- **Order value.** Item price plus freight, in Brazilian reais (R$).
- **RFM.** With 97% of buyers ordering once, standard 1 to 5 RFM scoring collapses. The segments instead use three cut-offs: returned or not, last order within 90 or 270 days, and lifetime spend in the top 20%.
- **Significance.** Each comparison uses a two-sided two-proportion z-test. Five tests are run, so the bar is p < 0.01 (Bonferroni).

## Rebuild it

```bash
cd projects/olist-customer-retention
pip install duckdb
python src/build.py     # downloads the CSVs (~125 MB) into raw/, then rebuilds data/
python -m http.server   # then open http://localhost:8000
```

## Data

Olist, [Brazilian E-Commerce Public Dataset](https://github.com/olist/work-at-olist-data), MIT licence.

## Built with

DuckDB (SQL), Python, HTML/CSS/JavaScript, [Chart.js](https://www.chartjs.org/). The cohort heatmap, state table, factor table and RFM table are plain HTML.
