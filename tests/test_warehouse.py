from ingomob.warehouse import query_df, table_exists


def test_star_schema_objects_exist(pipeline):
    for t in ("dim_date", "dim_detector", "dim_route", "dim_district", "fact_traffic",
              "fact_stop_departures", "fact_charging", "mart_route_service",
              "mart_district_scorecard", "mart_stop_service"):
        assert table_exists(t), f"{t} missing"


def test_referential_integrity(pipeline):
    orphans = query_df("""
        SELECT COUNT(*) c FROM fact_traffic f
        LEFT JOIN dim_detector d ON d.detector_key = f.detector_key
        WHERE d.detector_key IS NULL""")["c"][0]
    assert orphans == 0


def test_dates_are_typed_not_strings(pipeline):
    t = query_df("SELECT data_type FROM information_schema.columns "
                 "WHERE table_name='fact_traffic' AND column_name='date'")["data_type"][0]
    assert t.upper() == "DATE", f"fact_traffic.date should be DATE, is {t}"


def test_no_null_or_negative_counts(pipeline):
    bad = query_df("SELECT COUNT(*) c FROM fact_traffic "
                   "WHERE vehicle_count IS NULL OR vehicle_count < 0")["c"][0]
    assert bad == 0


def test_school_holiday_dimension_populated(pipeline):
    n = query_df("SELECT COUNT(*) c FROM dim_date WHERE is_school_holiday")["c"][0]
    assert n > 0


def test_headway_is_plausible(pipeline):
    df = query_df("SELECT avg_peak_headway_min h FROM mart_route_service")
    assert df["h"].between(3, 90).all(), "implausible headway values"
    assert df["h"].nunique() > 1, "all lines identical - service model is degenerate"
