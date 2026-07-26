-- ============================================================
-- Fact layer
-- ============================================================

CREATE OR REPLACE TABLE fact_traffic AS
SELECT
    dd.date_key,
    CAST(t.date AS DATE)  AS date,          -- typed, not VARCHAR
    CAST(t.hour AS INTEGER) AS hour,
    det.detector_key,
    dist.district_key,
    det.road_type,
    det.district,
    CAST(t.vehicle_count AS INTEGER) AS vehicle_count,
    CAST(w.temp_c AS DOUBLE)   AS temp_c,
    CAST(w.precip_mm AS DOUBLE) AS precip_mm,
    dd.is_holiday
FROM stg_traffic t
JOIN stg_weather w        ON CAST(w.date AS DATE) = CAST(t.date AS DATE)
                          AND CAST(w.hour AS INTEGER) = CAST(t.hour AS INTEGER)
JOIN dim_detector det     ON det.detector_id = t.detector_id
JOIN dim_date dd          ON dd.date = CAST(t.date AS DATE)
JOIN dim_district dist    ON dist.district = det.district;

CREATE OR REPLACE TABLE fact_stop_departures AS
SELECT
    r.route_key,
    tr.route_id,
    tr.service_id,
    s.stop_key,
    st.stop_id,
    st.stop_sequence,
    CAST(st.departure_time AS TIME) AS departure_time,
    EXTRACT(EPOCH FROM CAST(st.departure_time AS TIME)) / 60.0 AS dep_min
FROM stg_stop_times st
JOIN stg_trips tr    ON tr.trip_id = st.trip_id
JOIN dim_route r     ON r.route_id = tr.route_id
JOIN dim_stop s      ON s.stop_id  = st.stop_id;

CREATE OR REPLACE TABLE fact_charging AS
SELECT
    cs.station_key,
    cs.station_id,
    dist.district_key,
    cs.district,
    cs.num_points,
    cs.power_kw,
    cs.num_points * cs.power_kw AS total_kw,
    cs.install_year
FROM dim_charging_station cs
JOIN dim_district dist ON dist.district = cs.district;
