-- 01_clean.sql
-- Turns the raw City of Chicago export into two clean tables:
--   inspections : one row per inspection, typed and standardized
--   violations  : one row per violation cited, split out of the long text field
-- Expects two input tables: raw (the CSV, all columns as text) and loc_area
-- (latitude/longitude -> community area, built in Python by point-in-polygon).

CREATE OR REPLACE TABLE inspections AS
WITH typed AS (
    SELECT
        CAST("Inspection ID" AS BIGINT)                          AS inspection_id,
        NULLIF(NULLIF(TRIM("License #"), ''), '0')               AS license_no,
        TRIM("DBA Name")                                         AS business_name,
        UPPER(TRIM("Facility Type"))                             AS facility_type_raw,
        TRY_CAST(regexp_extract(Risk, 'Risk (\d)', 1) AS INT)    AS risk_level,
        UPPER(TRIM(Address))                                     AS address,
        LEFT(TRIM(Zip), 5)                                       AS zip,
        CAST(strptime("Inspection Date", '%m/%d/%Y') AS DATE)    AS inspection_date,
        UPPER(TRIM("Inspection Type"))                           AS inspection_type_raw,
        Results                                                  AS result,
        Violations                                               AS violations_text,
        TRY_CAST(Latitude AS DOUBLE)                             AS latitude,
        TRY_CAST(Longitude AS DOUBLE)                            AS longitude
    FROM raw
),
deduped AS (
    -- 225 groups of rows are exact repeats (same license, date, type, result and
    -- violations) under different inspection IDs. Keep the first ID of each.
    SELECT *
    FROM typed
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY license_no, business_name, inspection_date, inspection_type_raw, result, violations_text
        ORDER BY inspection_id
    ) = 1
)
SELECT
    d.inspection_id,
    d.license_no,
    d.business_name,
    -- 472 distinct free-text facility types collapse into 11 groups
    CASE
        WHEN facility_type_raw IS NULL                                   THEN 'Unknown'
        WHEN facility_type_raw LIKE '%RESTAURANT%'                       THEN 'Restaurant'
        WHEN facility_type_raw LIKE '%GROCERY%'                          THEN 'Grocery store'
        WHEN facility_type_raw LIKE '%SCHOOL%'
             AND facility_type_raw NOT LIKE '%COOKING%'                  THEN 'School'
        WHEN facility_type_raw LIKE '%DAYCARE%'
          OR facility_type_raw LIKE '%CHILDREN%'                         THEN 'Daycare / children''s services'
        WHEN facility_type_raw LIKE '%BAKERY%'                           THEN 'Bakery'
        WHEN facility_type_raw LIKE '%LONG TERM%'
          OR facility_type_raw LIKE '%HOSPITAL%'
          OR facility_type_raw LIKE '%NURSING%'
          OR facility_type_raw LIKE '%ASSISTED LIVING%'
          OR facility_type_raw LIKE '%SUPPORTIVE LIVING%'                THEN 'Hospital / long-term care'
        WHEN facility_type_raw LIKE '%MOBILE%'                           THEN 'Mobile food'
        WHEN facility_type_raw LIKE '%CATER%'                            THEN 'Catering'
        WHEN facility_type_raw LIKE '%TAVERN%'
          OR facility_type_raw LIKE '%LIQUOR%'
          OR facility_type_raw LIKE '%BAR'                               THEN 'Bar / tavern / liquor'
        ELSE 'Other'
    END                                                                  AS facility_group,
    d.facility_type_raw,
    d.risk_level,
    d.address,
    d.zip,
    d.inspection_date,
    -- inspection purpose, with re-inspections flagged separately
    CASE
        WHEN inspection_type_raw LIKE '%CANVAS%'                         THEN 'Canvass'
        WHEN inspection_type_raw LIKE '%LICENSE%'                        THEN 'License'
        WHEN inspection_type_raw LIKE '%COMPLAINT%'                      THEN 'Complaint'
        WHEN inspection_type_raw LIKE '%FOOD POISONING%'                 THEN 'Suspected food poisoning'
        ELSE 'Other'
    END                                                                  AS inspection_purpose,
    regexp_matches(inspection_type_raw, 'RE-?INSPECTION')                AS is_reinspection,
    d.inspection_type_raw,
    d.result,
    -- only Pass / Pass w/ Conditions / Fail are scored outcomes; the rest
    -- (Out of Business, No Entry, Not Ready...) mean no inspection happened
    d.result IN ('Pass', 'Pass w/ Conditions', 'Fail')                   AS is_scored,
    d.result = 'Fail'                                                    AS is_fail,
    -- Chicago switched to the FDA Food Code on 1 Jul 2018 and renumbered every violation
    CASE WHEN d.inspection_date >= DATE '2018-07-01' THEN 2018 ELSE 2012 END AS code_version,
    d.violations_text,
    d.latitude,
    d.longitude,
    la.community_area_no,
    la.community_area
FROM deduped d
LEFT JOIN loc_area la USING (latitude, longitude);


CREATE OR REPLACE TABLE violations AS
WITH split AS (
    SELECT
        inspection_id,
        code_version,
        UNNEST(string_split(violations_text, ' | ')) AS v
    FROM inspections
    WHERE violations_text IS NOT NULL
)
SELECT
    inspection_id,
    code_version,
    CAST(regexp_extract(v, '^(\d+)\.', 1) AS INT)                        AS violation_no,
    TRIM(regexp_extract(v, '^\d+\.\s*(.+?)(\s+-\s+Comments:|$)', 1))     AS violation_desc,
    NULLIF(TRIM(regexp_extract(v, 'Comments:\s*(.*)$', 1)), '')          AS inspector_comment
FROM split
WHERE regexp_matches(v, '^\d+\.');

-- inspectors tag each violation's severity in the free-text comment.
-- Priority (P) and priority foundation (PF) violations are the ones that can
-- fail an inspection; core violations are housekeeping. One comment can
-- carry both tags, so they are separate flags.
CREATE OR REPLACE TABLE violations AS
SELECT
    *,
    COALESCE(regexp_matches(UPPER(inspector_comment), 'PRIORITY VIOLATION'), FALSE)  AS is_priority,
    COALESCE(regexp_matches(UPPER(inspector_comment), 'PRIORITY FOUNDATION'), FALSE) AS is_priority_foundation
FROM violations;
