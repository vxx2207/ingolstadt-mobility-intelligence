import itertools

from ingomob import siting
from ingomob.transit_quality import summarize


def test_transit_summary_is_internally_consistent(pipeline):
    s = summarize(pipeline)
    assert s["n_routes"] > 0 and s["n_stops"] > 0
    assert s["best_route"]["headway_min"] <= s["worst_route"]["headway_min"]
    assert 0 < s["weekend_service_ratio_pct"] < 100
    assert s["n_underserved_stops"] <= s["n_stops"]
    assert s["method_note"], "metric must be self-documenting"


def test_siting_respects_its_own_spacing_constraint(pipeline):
    spacing = 1.2
    r = siting.recommend(n_recommend=8, min_spacing_km=spacing, settings=pipeline)
    recs = r["recommendations"]
    assert recs
    for a, b in itertools.combinations(recs, 2):
        d = siting._km(a["lat"], a["lon"], b["lat"], b["lon"])
        assert d >= spacing - 1e-6, f"recommendations {a['rank']}/{b['rank']} only {d:.2f} km apart"


def test_siting_scores_are_ordered_and_non_negative(pipeline):
    r = siting.recommend(settings=pipeline)
    gaps = [x["gap_score"] for x in r["recommendations"]]
    assert all(g >= 0 for g in gaps)
    assert gaps == sorted(gaps, reverse=True)


def test_siting_declares_its_caveats(pipeline):
    r = siting.recommend(settings=pipeline)
    assert r["caveats"], "a heuristic must state its limits"
    assert "heuristic" in r["method"].lower()
