# Data Dictionary

## Dimensions

### `dim_date`
| Column | Type | Notes |
|---|---|---|
| date_key | INT | surrogate key |
| date | DATE | |
| year, month, day | INT | |
| dow | INT | 0 = Sunday |
| day_name | VARCHAR | |
| is_weekend | BOOL | |
| is_holiday | BOOL | Bavarian public holidays |
| holiday_name | VARCHAR | nullable |
| season | VARCHAR | Winter/Spring/Summer |

### `dim_detector`
| Column | Type | Notes |
|---|---|---|
| detector_key | INT | surrogate key |
| detector_id | VARCHAR | natural key (e.g. `D001`) |
| detector_name | VARCHAR | |
| lat, lon | DOUBLE | WGS84 |
| road_type | VARCHAR | arterial/ring/collector/local |
| district | VARCHAR | |
| peak_base | INT | modelled peak vehicles/h |

### `dim_charging_station`
| Column | Type | Notes |
|---|---|---|
| station_key | INT | surrogate key |
| station_id | VARCHAR | natural key (`CS001`) |
| operator | VARCHAR | |
| lat, lon | DOUBLE | |
| num_points | INT | connectors |
| power_kw | INT | rated power |
| install_year | INT | |
| district | VARCHAR | |

Other dimensions: `dim_time` (hour, daypart, is_peak), `dim_district`
(district, centroid lat/lon), `dim_stop` (GTFS stop + district),
`dim_route` (GTFS route).

## Facts

### `fact_traffic` — grain: detector × date × hour
| Column | Type | Notes |
|---|---|---|
| date_key, detector_key, district_key | INT | foreign keys |
| date | VARCHAR | |
| hour | INT | 0–23 |
| road_type, district | VARCHAR | denormalised for speed |
| vehicle_count | INT | target variable |
| temp_c, precip_mm | DOUBLE | weather |
| is_holiday | BOOL | |

### `fact_stop_departures` — grain: trip × stop
| Column | Type | Notes |
|---|---|---|
| route_key, stop_key | INT | foreign keys |
| route_id, stop_id | VARCHAR | |
| service_id | VARCHAR | weekday/saturday/sunday |
| stop_sequence | INT | |
| departure_time | TIME | |
| dep_min | DOUBLE | minutes since midnight |

### `fact_charging` — grain: station
| Column | Type | Notes |
|---|---|---|
| station_key, district_key | INT | foreign keys |
| num_points, power_kw | INT | |
| total_kw | INT | num_points × power_kw |
| install_year | INT | |

## ML feature frame (`fact_traffic` → `features.py`)
Calendar (`hour, dow, month, is_weekend, is_holiday`), weather
(`temp_c, precip_mm`), detector level (`peak_base`, `road_type`, `detector_id`),
and autoregressive lags (`lag_24`, `lag_168`, `roll_mean_24`).
