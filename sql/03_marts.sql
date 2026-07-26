-- ============================================================
-- Analytical marts (consumed by dashboard, report, siting, ML)
-- ============================================================

CREATE OR REPLACE VIEW mart_hourly_profile AS
SELECT f.hour, f.road_type, dd.is_weekend,
       ROUND(AVG(f.vehicle_count), 1) AS avg_count
FROM fact_traffic f
JOIN dim_date dd ON dd.date_key = f.date_key
GROUP BY f.hour, f.road_type, dd.is_weekend;

CREATE OR REPLACE VIEW mart_daily_traffic AS
SELECT f.date, dd.dow, dd.is_weekend, dd.is_holiday, dd.holiday_name,
       SUM(f.vehicle_count) AS total_count
FROM fact_traffic f
JOIN dim_date dd ON dd.date_key = f.date_key
GROUP BY f.date, dd.dow, dd.is_weekend, dd.is_holiday, dd.holiday_name
ORDER BY f.date;

CREATE OR REPLACE VIEW mart_route_service AS
WITH tps AS (
    SELECT route_id, service_id, COUNT(*) AS n_trips
    FROM stg_trips GROUP BY route_id, service_id
),
piv AS (
    SELECT route_id,
        SUM(CASE WHEN service_id='weekday'  THEN n_trips ELSE 0 END) AS trips_weekday,
        SUM(CASE WHEN service_id='saturday' THEN n_trips ELSE 0 END) AS trips_saturday,
        SUM(CASE WHEN service_id='sunday'   THEN n_trips ELSE 0 END) AS trips_sunday
    FROM tps GROUP BY route_id
),
nst AS (
    SELECT route_id, COUNT(DISTINCT stop_id) AS n_stops
    FROM fact_stop_departures GROUP BY route_id
),
span AS (
    SELECT route_id, MAX(dep_min) - MIN(dep_min) AS span_min
    FROM fact_stop_departures
    WHERE service_id='weekday' AND stop_sequence = 1
    GROUP BY route_id
),
peak_deps AS (
    SELECT route_id, dep_min,
           dep_min - LAG(dep_min) OVER (PARTITION BY route_id ORDER BY dep_min) AS gap_min,
           (dep_min >= 420 AND dep_min < 540) AS morning_peak,
           (dep_min >= 960 AND dep_min < 1080) AS evening_peak
    FROM fact_stop_departures
    WHERE service_id='weekday' AND stop_sequence = 1
),
peak AS (
    -- true mean gap between consecutive departures inside the peak windows
    SELECT route_id,
           AVG(gap_min) AS mean_headway_min,
           COUNT(*)     AS peak_deps
    FROM peak_deps
    WHERE gap_min IS NOT NULL AND (morning_peak OR evening_peak)
    GROUP BY route_id
)
SELECT
    r.route_id, r.route_short_name, r.route_long_name,
    piv.trips_weekday, piv.trips_saturday, piv.trips_sunday,
    nst.n_stops,
    ROUND(span.span_min / 60.0, 1) AS span_hours,
    ROUND(peak.mean_headway_min, 1) AS avg_peak_headway_min
FROM dim_route r
JOIN piv  ON piv.route_id  = r.route_id
JOIN nst  ON nst.route_id  = r.route_id
JOIN span ON span.route_id = r.route_id
LEFT JOIN peak ON peak.route_id = r.route_id;

CREATE OR REPLACE VIEW mart_stop_service AS
SELECT s.stop_id, s.stop_name, s.district, s.lat, s.lon,
       COUNT(*) FILTER (WHERE fd.service_id='weekday') AS departures_weekday,
       COUNT(*) FILTER (WHERE fd.service_id='saturday') AS departures_saturday,
       COUNT(*) FILTER (WHERE fd.service_id='sunday')   AS departures_sunday,
       MIN(fd.departure_time) FILTER (WHERE fd.service_id='weekday') AS first_dep_weekday,
       MAX(fd.departure_time) FILTER (WHERE fd.service_id='weekday') AS last_dep_weekday
FROM dim_stop s
LEFT JOIN fact_stop_departures fd ON fd.stop_id = s.stop_id
GROUP BY s.stop_id, s.stop_name, s.district, s.lat, s.lon;

CREATE OR REPLACE VIEW mart_district_scorecard AS
WITH tr AS (
    SELECT district, AVG(daily) AS avg_daily_traffic FROM (
        SELECT det.district, f.date, SUM(f.vehicle_count) AS daily
        FROM fact_traffic f
        JOIN dim_detector det ON det.detector_key = f.detector_key
        GROUP BY det.district, f.date
    ) q GROUP BY district
),
ch AS (
    SELECT district, COUNT(*) AS n_stations, SUM(num_points) AS n_points,
           SUM(num_points * power_kw) AS total_kw
    FROM dim_charging_station GROUP BY district
),
det AS (SELECT district, COUNT(*) AS n_detectors FROM dim_detector GROUP BY district),
st  AS (SELECT district, COUNT(*) AS n_stops     FROM dim_stop     GROUP BY district),
dep AS (
    SELECT s.district, COUNT(*) FILTER (WHERE fd.service_id='weekday') AS weekday_departures
    FROM dim_stop s LEFT JOIN fact_stop_departures fd ON fd.stop_id = s.stop_id
    GROUP BY s.district
)
SELECT
    d.district, d.lat, d.lon,
    ROUND(COALESCE(tr.avg_daily_traffic, 0), 0) AS avg_daily_traffic,
    COALESCE(det.n_detectors, 0)        AS n_detectors,
    COALESCE(st.n_stops, 0)             AS n_stops,
    COALESCE(dep.weekday_departures, 0) AS weekday_departures,
    COALESCE(ch.n_stations, 0)          AS n_charging_stations,
    COALESCE(ch.n_points, 0)            AS n_charging_points,
    COALESCE(ch.total_kw, 0)            AS total_charging_kw,
    ROUND(COALESCE(ch.n_points, 0) * 100000.0
          / NULLIF(COALESCE(tr.avg_daily_traffic, 0), 0), 2) AS charging_per_100k_traffic
FROM dim_district d
LEFT JOIN tr  ON tr.district  = d.district
LEFT JOIN ch  ON ch.district  = d.district
LEFT JOIN det ON det.district = d.district
LEFT JOIN st  ON st.district  = d.district
LEFT JOIN dep ON dep.district = d.district;
