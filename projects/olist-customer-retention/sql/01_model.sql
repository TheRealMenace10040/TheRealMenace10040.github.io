-- 01_model.sql
-- Turn the 7 raw Olist tables (loaded by build.py as raw_*) into an analysis model:
--   order_fact      one row per order, with value, delivery timing and review
--   customer_orders one row per delivered order with the buyer's order sequence
--   first_orders    each buyer's first delivered order and whether they came back
--
-- Two things in this data trip people up:
--   * customer_id is new for every order. The person is customer_unique_id.
--   * Some orders have more than one review. Keep the latest answered one.

-- Latest review per order -----------------------------------------------------
CREATE OR REPLACE TABLE review_latest AS
SELECT order_id, review_score, review_comment_message
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY order_id
                              ORDER BY review_answer_timestamp DESC, review_creation_date DESC) AS rn
    FROM raw_order_reviews
)
WHERE rn = 1;

-- Item totals and the order's main category (the highest-priced item) ----------
CREATE OR REPLACE TABLE order_items_agg AS
WITH items AS (
    SELECT i.order_id, i.price, i.freight_value, i.seller_id,
           COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
           ROW_NUMBER() OVER (PARTITION BY i.order_id ORDER BY i.price DESC, i.order_item_id) AS rn
    FROM raw_order_items i
    LEFT JOIN raw_products p USING (product_id)
    LEFT JOIN raw_category_translation t USING (product_category_name)
)
SELECT order_id,
       COUNT(*)                                  AS items,
       SUM(price)                                AS item_value,
       SUM(freight_value)                        AS freight_value,
       SUM(price + freight_value)                AS gmv,
       COUNT(DISTINCT seller_id)                 AS sellers,
       MAX(CASE WHEN rn = 1 THEN category END)   AS main_category,
       MAX(CASE WHEN rn = 1 THEN seller_id END)  AS main_seller_id
FROM items
GROUP BY order_id;

-- Order fact -------------------------------------------------------------------
CREATE OR REPLACE TABLE order_fact AS
SELECT o.order_id,
       c.customer_unique_id,
       c.customer_state,
       o.order_status,
       o.order_purchase_timestamp                                   AS purchased_at,
       DATE_TRUNC('month', o.order_purchase_timestamp)::DATE         AS purchase_month,
       o.order_delivered_customer_date                              AS delivered_at,
       o.order_estimated_delivery_date                              AS promised_at,
       DATE_DIFF('day', o.order_purchase_timestamp, o.order_delivered_customer_date)            AS days_to_deliver,
       DATE_DIFF('day', o.order_estimated_delivery_date::DATE, o.order_delivered_customer_date::DATE) AS days_late,
       o.order_delivered_customer_date::DATE > o.order_estimated_delivery_date::DATE             AS is_late,
       a.items, a.item_value, a.freight_value, a.gmv, a.sellers,
       a.main_category,
       s.seller_state AS main_seller_state,
       r.review_score
FROM raw_orders o
JOIN raw_customers c          USING (customer_id)
LEFT JOIN order_items_agg a   USING (order_id)
LEFT JOIN raw_sellers s       ON s.seller_id = a.main_seller_id
LEFT JOIN review_latest r     USING (order_id);

-- Analysis window: Jan 2017 to Aug 2018. Before 2017 the marketplace was still
-- ramping up (a few hundred orders); after Aug 2018 the export is cut off.
CREATE OR REPLACE TABLE delivered AS
SELECT *
FROM order_fact
WHERE order_status = 'delivered'
  AND delivered_at IS NOT NULL
  AND purchase_month BETWEEN DATE '2017-01-01' AND DATE '2018-08-01';

-- Each buyer's delivered orders in sequence --------------------------------------
CREATE OR REPLACE TABLE customer_orders AS
SELECT *,
       ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY purchased_at, order_id) AS order_seq,
       FIRST_VALUE(purchase_month) OVER (PARTITION BY customer_unique_id ORDER BY purchased_at, order_id) AS cohort_month
FROM delivered;

-- First order per buyer, and whether they came back ------------------------------
-- A return counts if the buyer placed another order on a later day, within 180
-- days of the first. Same-day second orders are left out: most are a basket
-- split into two checkouts, not a customer coming back.
-- Only buyers whose first order is at least 180 days before the data cutoff are
-- eligible, so recent buyers aren't counted as lost just because time ran out.
CREATE OR REPLACE TABLE first_orders AS
WITH cutoff AS (SELECT MAX(purchased_at) AS data_end FROM delivered),
firsts AS (SELECT * FROM customer_orders WHERE order_seq = 1),
nxt AS (
    SELECT f.customer_unique_id, MIN(o.purchased_at) AS return_at
    FROM firsts f
    JOIN customer_orders o
      ON o.customer_unique_id = f.customer_unique_id
     AND o.purchased_at::DATE > f.purchased_at::DATE
    GROUP BY 1
)
SELECT f.*,
       n.return_at,
       f.purchased_at <= cutoff.data_end - INTERVAL 180 DAY                       AS eligible_180,
       n.return_at IS NOT NULL
         AND n.return_at <= f.purchased_at + INTERVAL 180 DAY                       AS repeat_180
FROM firsts f
CROSS JOIN cutoff
LEFT JOIN nxt n USING (customer_unique_id);
