-- ============================================================
-- Dimension layer (star schema) - conformed dimensions
-- ============================================================

CREATE OR REPLACE TABLE dim_date AS
WITH days AS (
    SELECT CAST(g AS DATE) AS date
    FROM range(TIMESTAMP '2025-01-01', TIMESTAMP '2025-06-30', INTERVAL 1 DAY) t(g)
),
school(start_date, end_date) AS (
    VALUES (DATE '2025-01-01', DATE '2025-01-06'),
           (DATE '2025-03-03', DATE '2025-03-07'),
           (DATE '2025-04-14', DATE '2025-04-25'),
           (DATE '2025-06-10', DATE '2025-06-20')
),
hol(date, holiday_name) AS (
    VALUES (DATE '2025-01-01','Neujahr'),
           (DATE '2025-01-06','Heilige Drei Koenige'),
           (DATE '2025-04-18','Karfreitag'),
           (DATE '2025-04-21','Ostermontag'),
           (DATE '2025-05-01','Tag der Arbeit'),
           (DATE '2025-05-29','Christi Himmelfahrt'),
           (DATE '2025-06-09','Pfingstmontag'),
           (DATE '2025-06-19','Fronleichnam')
)
SELECT
    ROW_NUMBER() OVER (ORDER BY d.date) AS date_key,
    d.date,
    EXTRACT(year  FROM d.date) AS year,
    EXTRACT(month FROM d.date) AS month,
    EXTRACT(day   FROM d.date) AS day,
    EXTRACT(dow   FROM d.date) AS dow,           -- 0 = Sunday
    DAYNAME(d.date)            AS day_name,
    (EXTRACT(dow FROM d.date) IN (0, 6))              AS is_weekend,
    (h.date IS NOT NULL)                              AS is_holiday,
    EXISTS (SELECT 1 FROM school sc
            WHERE d.date BETWEEN sc.start_date AND sc.end_date) AS is_school_holiday,
    h.holiday_name,
    CASE WHEN EXTRACT(month FROM d.date) IN (12,1,2) THEN 'Winter'
         WHEN EXTRACT(month FROM d.date) IN (3,4,5)  THEN 'Spring'
         ELSE 'Summer' END AS season
FROM days d
LEFT JOIN hol h ON h.date = d.date;

CREATE OR REPLACE TABLE dim_time AS
SELECT
    h AS hour,
    CASE WHEN h < 6  THEN 'Night'
         WHEN h < 10 THEN 'Morning'
         WHEN h < 14 THEN 'Midday'
         WHEN h < 18 THEN 'Afternoon'
         WHEN h < 22 THEN 'Evening'
         ELSE 'Night' END AS daypart,
    (h IN (7,8,16,17)) AS is_peak
FROM range(0, 24) t(h);

CREATE OR REPLACE TABLE dim_district AS
WITH pts AS (
    SELECT d.district, s.stop_lat AS lat, s.stop_lon AS lon
    FROM stg_stops s JOIN stg_stop_districts d USING (stop_id)
    UNION ALL SELECT district, lat, lon FROM stg_charging
    UNION ALL SELECT district, lat, lon FROM stg_detectors
)
SELECT ROW_NUMBER() OVER (ORDER BY district) AS district_key,
       district,
       ROUND(AVG(lat), 6) AS lat,
       ROUND(AVG(lon), 6) AS lon
FROM pts GROUP BY district;

CREATE OR REPLACE TABLE dim_stop AS
SELECT ROW_NUMBER() OVER (ORDER BY s.stop_id) AS stop_key,
       s.stop_id, s.stop_name, s.stop_lat AS lat, s.stop_lon AS lon, d.district
FROM stg_stops s
LEFT JOIN stg_stop_districts d USING (stop_id);

CREATE OR REPLACE TABLE dim_route AS
SELECT ROW_NUMBER() OVER (ORDER BY route_id) AS route_key,
       route_id, route_short_name, route_long_name, route_type
FROM stg_routes;

CREATE OR REPLACE TABLE dim_detector AS
SELECT ROW_NUMBER() OVER (ORDER BY detector_id) AS detector_key,
       detector_id, name AS detector_name, lat, lon, road_type, district, peak_base
FROM stg_detectors;

CREATE OR REPLACE TABLE dim_charging_station AS
SELECT ROW_NUMBER() OVER (ORDER BY station_id) AS station_key,
       station_id, name AS station_name, operator, lat, lon,
       num_points, power_kw, install_year, district
FROM stg_charging;
