-- 02_analysis.sql
-- Analysis tables behind the dashboard. Each table here is exported to data/<name>.csv.
-- Runs after 01_model.sql.

-- Headline numbers ----------------------------------------------------------------
CREATE OR REPLACE TABLE kpis AS
WITH buyers AS (
    SELECT customer_unique_id,
           COUNT(*)                              AS orders,
           COUNT(DISTINCT purchased_at::DATE)    AS order_days
    FROM delivered GROUP BY 1
)
SELECT
    (SELECT COUNT(*) FROM delivered)                                         AS orders,
    (SELECT COUNT(*) FROM buyers)                                            AS buyers,
    (SELECT ROUND(SUM(gmv), 2) FROM delivered)                               AS gmv,
    (SELECT ROUND(AVG(gmv), 2) FROM delivered)                               AS avg_order_value,
    (SELECT ROUND(AVG(is_late::INT), 4) FROM delivered)                      AS late_rate,
    (SELECT ROUND(AVG(review_score), 2) FROM delivered)                      AS avg_review,
    (SELECT ROUND(AVG((orders > 1)::INT), 4) FROM buyers)                    AS naive_repeat_rate,
    (SELECT ROUND(AVG((order_days > 1)::INT), 4) FROM buyers)                AS any_return_rate,
    (SELECT COUNT(*) FROM first_orders WHERE eligible_180)                   AS eligible_buyers,
    (SELECT SUM(repeat_180::INT) FROM first_orders WHERE eligible_180)       AS returned_180,
    (SELECT ROUND(AVG(repeat_180::INT), 4) FROM first_orders WHERE eligible_180) AS repeat_180_rate,
    (SELECT ROUND(SUM(gmv) FILTER (WHERE order_seq = 1) / SUM(gmv), 4) FROM customer_orders) AS first_order_gmv_share,
    (SELECT MIN(purchased_at)::DATE FROM delivered)                          AS data_start,
    (SELECT MAX(purchased_at)::DATE FROM delivered)                          AS data_end;

-- Month by month --------------------------------------------------------------------
CREATE OR REPLACE TABLE monthly AS
SELECT purchase_month                                         AS month,
       COUNT(*)                                               AS orders,
       ROUND(SUM(gmv), 2)                                     AS gmv,
       COUNT(*) FILTER (WHERE order_seq = 1)                  AS first_orders,
       COUNT(*) FILTER (WHERE order_seq > 1)                  AS repeat_orders,
       ROUND(AVG(is_late::INT), 4)                            AS late_rate,
       ROUND(AVG(review_score), 2)                            AS avg_review
FROM customer_orders
GROUP BY 1 ORDER BY 1;

-- Monthly cohort retention ------------------------------------------------------------
-- Share of each month's new buyers who ordered again 1, 2, 3 ... months later.
-- Month 0 repeat orders are not shown, because same-month repeats are mostly split baskets.
CREATE OR REPLACE TABLE cohort AS
WITH sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_unique_id) AS buyers
    FROM customer_orders GROUP BY 1
),
active AS (
    SELECT cohort_month,
           DATE_DIFF('month', cohort_month, purchase_month) AS month_offset,
           COUNT(DISTINCT customer_unique_id)               AS active_buyers
    FROM customer_orders
    WHERE purchase_month > cohort_month
    GROUP BY 1, 2
)
SELECT s.cohort_month, s.buyers, a.month_offset, a.active_buyers,
       ROUND(a.active_buyers / s.buyers, 5) AS retention
FROM sizes s
JOIN active a USING (cohort_month)
WHERE a.month_offset <= 12
ORDER BY 1, 3;

-- How late a delivery was vs. the review it got ------------------------------------------
CREATE OR REPLACE TABLE late_vs_review AS
SELECT CASE WHEN days_late <= 0  THEN 0
            WHEN days_late <= 3  THEN 1
            WHEN days_late <= 7  THEN 2
            WHEN days_late <= 14 THEN 3
            ELSE 4 END                                                     AS bucket_order,
       CASE WHEN days_late <= 0  THEN 'On time or early'
            WHEN days_late <= 3  THEN '1 to 3 days late'
            WHEN days_late <= 7  THEN '4 to 7 days late'
            WHEN days_late <= 14 THEN '8 to 14 days late'
            ELSE '15+ days late' END                                       AS bucket,
       COUNT(*)                                                            AS orders,
       ROUND(AVG(review_score), 2)                                         AS avg_review,
       ROUND(AVG((review_score <= 2)::INT), 4)                             AS negative_share,
       ROUND(AVG((review_score = 5)::INT), 4)                              AS five_star_share
FROM delivered
WHERE review_score IS NOT NULL
GROUP BY 1, 2 ORDER BY 1;

-- Where late deliveries happen: by customer state --------------------------------------------
CREATE OR REPLACE TABLE late_by_state AS
SELECT customer_state                                  AS state,
       COUNT(*)                                        AS orders,
       ROUND(AVG(is_late::INT), 4)                     AS late_rate,
       ROUND(MEDIAN(days_to_deliver), 1)               AS median_days_to_deliver,
       ROUND(AVG(review_score), 2)                     AS avg_review,
       ROUND(AVG((customer_state <> main_seller_state)::INT), 4) AS interstate_share
FROM delivered
GROUP BY 1 ORDER BY late_rate DESC;

-- Same-state vs. interstate shipping ------------------------------------------------------------
CREATE OR REPLACE TABLE late_by_route AS
SELECT CASE WHEN customer_state = main_seller_state THEN 'Same state' ELSE 'Interstate' END AS route,
       COUNT(*)                                        AS orders,
       ROUND(AVG(is_late::INT), 4)                     AS late_rate,
       ROUND(MEDIAN(days_to_deliver), 1)               AS median_days_to_deliver,
       ROUND(AVG(review_score), 2)                     AS avg_review
FROM delivered
WHERE main_seller_state IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- Does the first experience predict coming back? ------------------------------------------------
-- Eligible first-time buyers only (first order at least 180 days before cutoff).
CREATE OR REPLACE TABLE repeat_by_first AS
WITH f AS (SELECT * FROM first_orders WHERE eligible_180),
q AS (SELECT *, NTILE(5) OVER (ORDER BY gmv) AS value_q FROM f)
SELECT 'Delivery' AS factor, 1 AS level_order,
       CASE WHEN is_late THEN 'Late' ELSE 'On time' END AS level,
       COUNT(*) AS buyers, SUM(repeat_180::INT) AS returned, ROUND(AVG(repeat_180::INT), 5) AS repeat_rate
FROM f GROUP BY 3
UNION ALL
SELECT 'Review', 2,
       CASE WHEN review_score >= 4 THEN '4 or 5 stars' WHEN review_score <= 2 THEN '1 or 2 stars' ELSE '3 stars' END,
       COUNT(*), SUM(repeat_180::INT), ROUND(AVG(repeat_180::INT), 5)
FROM f WHERE review_score IS NOT NULL GROUP BY 3
UNION ALL
SELECT 'Route', 3,
       CASE WHEN customer_state = main_seller_state THEN 'Same state' ELSE 'Interstate' END,
       COUNT(*), SUM(repeat_180::INT), ROUND(AVG(repeat_180::INT), 5)
FROM f WHERE main_seller_state IS NOT NULL GROUP BY 3
UNION ALL
SELECT 'First order value', 4, 'Quintile ' || value_q,
       COUNT(*), SUM(repeat_180::INT), ROUND(AVG(repeat_180::INT), 5)
FROM q GROUP BY 3
ORDER BY 2, 3;

-- Repeat rate by the category of the first order ------------------------------------------------
CREATE OR REPLACE TABLE repeat_by_category AS
SELECT main_category                                   AS category,
       COUNT(*)                                        AS buyers,
       SUM(repeat_180::INT)                            AS returned,
       ROUND(AVG(repeat_180::INT), 5)                  AS repeat_rate,
       ROUND(AVG(gmv), 2)                              AS avg_first_order_value,
       -- share of returners whose next order was in the same category
       ROUND(AVG(CASE WHEN repeat_180 THEN (next_category = main_category)::INT END), 4) AS same_category_share
FROM (
    SELECT f.*, n.main_category AS next_category
    FROM first_orders f
    LEFT JOIN customer_orders n
      ON n.customer_unique_id = f.customer_unique_id AND n.purchased_at = f.return_at
    WHERE f.eligible_180
    QUALIFY ROW_NUMBER() OVER (PARTITION BY f.customer_unique_id ORDER BY n.order_id) = 1
)
GROUP BY 1
HAVING COUNT(*) >= 800
ORDER BY repeat_rate DESC;

-- How long until a returning buyer comes back ---------------------------------------------------------
CREATE OR REPLACE TABLE return_gap AS
SELECT CASE WHEN d <= 30 THEN 1 WHEN d <= 60 THEN 2 WHEN d <= 90 THEN 3
            WHEN d <= 180 THEN 4 ELSE 5 END                       AS bucket_order,
       CASE WHEN d <= 30 THEN '1 to 30 days' WHEN d <= 60 THEN '31 to 60 days'
            WHEN d <= 90 THEN '61 to 90 days' WHEN d <= 180 THEN '91 to 180 days'
            ELSE 'Over 180 days' END                              AS gap,
       COUNT(*)                                                   AS buyers
FROM (SELECT DATE_DIFF('day', purchased_at, return_at) AS d FROM first_orders WHERE return_at IS NOT NULL)
GROUP BY 1, 2 ORDER BY 1;

-- RFM segments ------------------------------------------------------------------------------------------
-- With ~97% of buyers ordering once, classic 5x5x5 RFM scoring collapses. Instead:
--   F: returned on a later day or not
--   R: days since last order, as of the data cutoff (0-90 / 91-270 / 270+)
--   M: lifetime spend in the top 20% of buyers or not
CREATE OR REPLACE TABLE rfm_customers AS
WITH b AS (
    SELECT customer_unique_id,
           COUNT(DISTINCT purchased_at::DATE)                                       AS frequency,
           DATE_DIFF('day', MAX(purchased_at), (SELECT MAX(purchased_at) FROM delivered)) AS recency_days,
           SUM(gmv)                                                                 AS monetary
    FROM delivered GROUP BY 1
),
s AS (SELECT *, PERCENT_RANK() OVER (ORDER BY monetary) AS m_pct FROM b)
SELECT *,
       CASE
           WHEN frequency >= 2 AND recency_days <= 270 THEN 'Repeat, active'
           WHEN frequency >= 2                         THEN 'Repeat, lapsed'
           WHEN recency_days <= 90  AND m_pct >= 0.8   THEN 'New, high value'
           WHEN recency_days <= 90                     THEN 'New'
           WHEN recency_days <= 270 AND m_pct >= 0.8   THEN 'One-time, high value, cooling'
           WHEN recency_days <= 270                    THEN 'One-time, cooling'
           WHEN m_pct >= 0.8                           THEN 'One-time, high value, lost'
           ELSE 'One-time, lost'
       END AS segment
FROM s;

CREATE OR REPLACE TABLE rfm AS
SELECT segment,
       COUNT(*)                                                 AS buyers,
       ROUND(COUNT(*) / SUM(COUNT(*)) OVER (), 4)               AS buyer_share,
       ROUND(SUM(monetary), 2)                                  AS gmv,
       ROUND(SUM(monetary) / SUM(SUM(monetary)) OVER (), 4)     AS gmv_share,
       ROUND(AVG(recency_days), 0)                              AS avg_recency_days,
       ROUND(AVG(frequency), 2)                                 AS avg_frequency,
       ROUND(AVG(monetary), 2)                                  AS avg_spend
FROM rfm_customers
GROUP BY 1
ORDER BY CASE segment
    WHEN 'Repeat, active' THEN 1 WHEN 'Repeat, lapsed' THEN 2
    WHEN 'New, high value' THEN 3 WHEN 'New' THEN 4
    WHEN 'One-time, high value, cooling' THEN 5 WHEN 'One-time, cooling' THEN 6
    WHEN 'One-time, high value, lost' THEN 7 ELSE 8 END;

-- Top categories by revenue -------------------------------------------------------------------------------
CREATE OR REPLACE TABLE categories AS
SELECT main_category                             AS category,
       COUNT(*)                                  AS orders,
       ROUND(SUM(gmv), 2)                        AS gmv,
       ROUND(AVG(gmv), 2)                        AS avg_order_value,
       ROUND(AVG(is_late::INT), 4)               AS late_rate,
       ROUND(AVG(review_score), 2)               AS avg_review
FROM delivered
GROUP BY 1
ORDER BY gmv DESC
LIMIT 15;
