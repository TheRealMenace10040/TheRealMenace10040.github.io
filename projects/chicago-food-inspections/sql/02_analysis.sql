-- 02_analysis.sql
-- Every out_* table becomes a CSV in data/ and a block in dashboard.json.
-- Scope: inspections from 1 Jul 2018 (when Chicago adopted the FDA Food Code and
-- renumbered violations) to the latest date in the download.
-- "Fail rate" = Fail / (Pass + Pass w/ Conditions + Fail). Out of Business,
-- No Entry and Not Ready are visits where no inspection could happen.
-- Most tables use GROUPING SETS so the dashboard gets every facility group
-- plus an 'All' row from one pass over the data.

CREATE OR REPLACE VIEW scored AS
SELECT *
FROM inspections
WHERE is_scored AND code_version = 2018;


-- 1. Headline numbers -------------------------------------------------------
CREATE OR REPLACE TABLE out_kpis AS
SELECT
    COALESCE(facility_group, 'All')                         AS facility_group,
    COUNT(*)                                                AS inspections,
    COUNT(DISTINCT license_no)                              AS businesses,
    SUM(is_fail::INT)                                       AS fails,
    ROUND(AVG(is_fail::INT), 4)                             AS fail_rate,
    MIN(inspection_date)                                    AS first_date,
    MAX(inspection_date)                                    AS last_date
FROM scored
GROUP BY GROUPING SETS ((facility_group), ())
ORDER BY inspections DESC;


-- 2. Monthly trend ----------------------------------------------------------
CREATE OR REPLACE TABLE out_monthly AS
SELECT
    COALESCE(facility_group, 'All')                         AS facility_group,
    strftime(date_trunc('month', inspection_date), '%Y-%m') AS month,
    COUNT(*)                                                AS inspections,
    ROUND(AVG(is_fail::INT), 4)                             AS fail_rate
FROM scored
GROUP BY GROUPING SETS ((facility_group, date_trunc('month', inspection_date)),
                        (date_trunc('month', inspection_date)))
ORDER BY facility_group, month;


-- 3. Which violations predict a failed inspection? --------------------------
-- For each violation: fail rate when it is cited vs. when it isn't, and the
-- lift (how many times more likely a fail is when it shows up).
CREATE OR REPLACE TABLE out_violations AS
WITH cited AS (                                   -- one row per inspection x violation number
    SELECT DISTINCT v.inspection_id, v.violation_no
    FROM violations v
    WHERE v.code_version = 2018
),
labels AS (                                       -- most common wording of each number
    SELECT violation_no, mode(violation_desc) AS violation_desc
    FROM violations
    WHERE code_version = 2018
    GROUP BY violation_no
),
group_totals AS (
    SELECT
        COALESCE(facility_group, 'All')           AS facility_group,
        COUNT(*)                                  AS n_all,
        SUM(is_fail::INT)                         AS fails_all
    FROM scored
    GROUP BY GROUPING SETS ((facility_group), ())
),
per_violation AS (
    SELECT
        COALESCE(s.facility_group, 'All')         AS facility_group,
        c.violation_no,
        COUNT(*)                                  AS n_cited,
        SUM(s.is_fail::INT)                       AS fails_cited
    FROM cited c
    JOIN scored s USING (inspection_id)
    GROUP BY GROUPING SETS ((s.facility_group, c.violation_no), (c.violation_no))
)
SELECT
    p.facility_group,
    p.violation_no,
    l.violation_desc,
    p.n_cited,
    ROUND(p.n_cited / g.n_all, 4)                                         AS cited_share,
    ROUND(p.fails_cited / p.n_cited, 4)                                   AS fail_rate_cited,
    ROUND((g.fails_all - p.fails_cited) / NULLIF(g.n_all - p.n_cited, 0), 4) AS fail_rate_not_cited,
    ROUND((p.fails_cited / p.n_cited)
          / NULLIF((g.fails_all - p.fails_cited) / NULLIF(g.n_all - p.n_cited, 0), 0), 2) AS lift,
    ROUND(p.fails_cited / g.fails_all, 4)                                 AS share_of_fails
FROM per_violation p
JOIN group_totals g USING (facility_group)
JOIN labels l USING (violation_no)
ORDER BY facility_group, lift DESC;


-- 4. Severity: do priority violations decide the result? --------------------
CREATE OR REPLACE TABLE out_severity AS
WITH flags AS (
    SELECT
        s.inspection_id,
        s.facility_group,
        s.is_fail,
        COALESCE(BOOL_OR(v.is_priority), FALSE)            AS has_p,
        COALESCE(BOOL_OR(v.is_priority_foundation), FALSE) AS has_pf,
        COUNT(v.violation_no)                             AS n_violations
    FROM scored s
    LEFT JOIN violations v USING (inspection_id)
    GROUP BY ALL
)
SELECT
    COALESCE(facility_group, 'All')                       AS facility_group,
    CASE
        WHEN has_p AND has_pf THEN '3 Priority and priority foundation'
        WHEN has_p            THEN '2 Priority only'
        WHEN has_pf           THEN '1 Priority foundation only'
        ELSE                       '0 Core violations only, or none'
    END                                                   AS severity_mix,
    COUNT(*)                                              AS inspections,
    ROUND(AVG(is_fail::INT), 4)                           AS fail_rate,
    ROUND(AVG(n_violations), 1)                           AS avg_violations
FROM flags
GROUP BY GROUPING SETS ((facility_group, severity_mix), (severity_mix))
ORDER BY facility_group, severity_mix;


-- 5. Do re-inspections pass? ------------------------------------------------
-- For every failed inspection, LEAD() finds the same business's next visit.
-- A next visit within 120 days counts as the re-inspection.
CREATE OR REPLACE TABLE out_reinspection AS
WITH visits AS (
    SELECT
        license_no,
        facility_group,
        inspection_date,
        result,
        code_version,
        LEAD(inspection_date) OVER w AS next_date,
        LEAD(result)          OVER w AS next_result
    FROM inspections
    WHERE license_no IS NOT NULL
    WINDOW w AS (PARTITION BY license_no ORDER BY inspection_date, inspection_id)
),
fails AS (
    SELECT
        *,
        date_diff('day', inspection_date, next_date) AS days_to_next
    FROM visits
    WHERE result = 'Fail'
      AND code_version = 2018
      AND inspection_date <= (SELECT MAX(inspection_date) FROM inspections) - INTERVAL 120 DAY   -- give every fail a full 120 days
)
SELECT
    COALESCE(facility_group, 'All')                                   AS facility_group,
    CASE
        WHEN days_to_next IS NULL OR days_to_next > 120 THEN '5 No follow-up within 120 days'
        WHEN next_result = 'Pass'                       THEN '1 Passed'
        WHEN next_result = 'Pass w/ Conditions'         THEN '2 Passed with conditions'
        WHEN next_result = 'Fail'                       THEN '3 Failed again'
        ELSE                                                 '4 Closed, not ready or no entry'
    END                                                               AS outcome,
    COUNT(*)                                                          AS fails,
    ROUND(COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY COALESCE(facility_group, 'All')), 4) AS share,
    MEDIAN(days_to_next) FILTER (WHERE days_to_next <= 120)           AS median_days
FROM fails
GROUP BY GROUPING SETS ((facility_group, outcome), (outcome))
ORDER BY facility_group, outcome;


-- Days from a fail to the re-inspection, in weekly bins (All facilities)
CREATE OR REPLACE TABLE out_reinspection_days AS
WITH visits AS (
    SELECT
        result,
        code_version,
        date_diff('day', inspection_date,
                  LEAD(inspection_date) OVER (PARTITION BY license_no ORDER BY inspection_date, inspection_id)) AS days_to_next
    FROM inspections
    WHERE license_no IS NOT NULL
)
SELECT
    LEAST(days_to_next // 7, 17) AS week,          -- week 17 = 119-120 days
    COUNT(*)                     AS fails
FROM visits
WHERE result = 'Fail' AND code_version = 2018 AND days_to_next <= 120
GROUP BY ALL
ORDER BY week;


-- 6. Does one routine inspection predict the next? --------------------------
-- LAG() over each business's canvass (routine) inspections, re-inspections excluded.
CREATE OR REPLACE TABLE out_next_canvass AS
WITH canvass AS (
    SELECT
        facility_group,
        is_fail,
        LAG(result) OVER (PARTITION BY license_no ORDER BY inspection_date, inspection_id) AS previous_result
    FROM scored
    WHERE inspection_purpose = 'Canvass'
      AND NOT is_reinspection
      AND license_no IS NOT NULL
)
SELECT
    COALESCE(facility_group, 'All')       AS facility_group,
    previous_result,
    COUNT(*)                              AS inspections,
    ROUND(AVG(is_fail::INT), 4)           AS fail_rate
FROM canvass
WHERE previous_result IS NOT NULL
GROUP BY GROUPING SETS ((facility_group, previous_result), (previous_result))
ORDER BY facility_group, previous_result;


-- 7. Facility types x inspection purpose ------------------------------------
CREATE OR REPLACE TABLE out_facility AS
SELECT
    facility_group,
    COALESCE(CASE WHEN is_reinspection THEN 'Re-inspection' ELSE inspection_purpose END, 'All') AS purpose,
    COUNT(*)                              AS inspections,
    ROUND(AVG(is_fail::INT), 4)           AS fail_rate
FROM scored
GROUP BY GROUPING SETS ((facility_group, CASE WHEN is_reinspection THEN 'Re-inspection' ELSE inspection_purpose END),
                        (facility_group))
ORDER BY facility_group, purpose;


-- 8. Neighborhoods (Chicago's 77 community areas) ---------------------------
-- Only first-time visits (no re-inspections), so areas with lots of
-- follow-ups don't look better than they are.
CREATE OR REPLACE TABLE out_areas AS
WITH a AS (
    SELECT
        COALESCE(facility_group, 'All')   AS facility_group,
        community_area_no,
        ANY_VALUE(community_area)         AS community_area,
        COUNT(*)                          AS inspections,
        ROUND(AVG(is_fail::INT), 4)       AS fail_rate,
        ROUND(AVG((inspection_purpose = 'Complaint')::INT), 4) AS complaint_share
    FROM scored
    WHERE community_area_no IS NOT NULL
      AND NOT is_reinspection
    GROUP BY GROUPING SETS ((facility_group, community_area_no), (community_area_no))
)
SELECT
    *,
    -- rank only areas with enough inspections to trust the rate
    CASE WHEN inspections >= 100 THEN
        RANK() OVER (PARTITION BY facility_group, inspections >= 100 ORDER BY fail_rate DESC)
    END AS fail_rank
FROM a
ORDER BY facility_group, fail_rank NULLS LAST;
