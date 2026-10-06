-- 1. Classify every result against its limits
CREATE VIEW v_results AS
SELECT s.*,
       CASE WHEN s.cfu >= l.action_limit THEN 'Action'
            WHEN s.cfu >= l.alert_limit  THEN 'Alert'
            ELSE 'Pass' END AS result_status
FROM em_samples s
JOIN limits l USING (sample_type);

-- 2. Monthly excursion rate by room
-- name: monthly_room_excursions
SELECT strftime('%Y-%m', sample_date)                          AS month,
       room,
       COUNT(*)                                                AS samples,
       SUM(result_status = 'Alert')                            AS alerts,
       SUM(result_status = 'Action')                           AS actions,
       ROUND(100.0 * SUM(result_status <> 'Pass') / COUNT(*), 2) AS excursion_pct
FROM v_results
GROUP BY month, room
ORDER BY month, room;

-- 3. Rooms whose excursion rate in the last 30 days is above their prior 90-day baseline
-- name: rooms_trending_up
WITH recent AS (
    SELECT room, AVG(result_status <> 'Pass') AS rate
    FROM v_results
    WHERE sample_date >  date((SELECT MAX(sample_date) FROM em_samples), '-30 day')
    GROUP BY room
), baseline AS (
    SELECT room, AVG(result_status <> 'Pass') AS rate
    FROM v_results
    WHERE sample_date <= date((SELECT MAX(sample_date) FROM em_samples), '-30 day')
      AND sample_date >  date((SELECT MAX(sample_date) FROM em_samples), '-120 day')
    GROUP BY room
)
SELECT r.room,
       ROUND(100 * b.rate, 2) AS baseline_pct,
       ROUND(100 * r.rate, 2) AS last30_pct,
       ROUND(100 * (r.rate - b.rate), 2) AS change_pts
FROM recent r JOIN baseline b USING (room)
WHERE r.rate > b.rate
ORDER BY change_pts DESC;

-- 4. Repeat excursions: same room + sample type exceeding a limit 3+ times in 14 days
-- name: repeat_excursions
SELECT a.room, a.sample_type, a.sample_date,
       COUNT(*) AS excursions_in_14_days
FROM v_results a
JOIN v_results b
  ON  b.room = a.room AND b.sample_type = a.sample_type
  AND b.result_status <> 'Pass'
  AND b.sample_date BETWEEN date(a.sample_date, '-13 day') AND a.sample_date
WHERE a.result_status <> 'Pass'
GROUP BY a.sample_id
HAVING COUNT(*) >= 3
ORDER BY a.sample_date;
