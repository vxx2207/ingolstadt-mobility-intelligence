"""Determinism is claimed in the README, so it is verified by content hash -
not by comparing row counts, which would pass even if values differed.
"""
from __future__ import annotations

import hashlib

from ingomob.sources.demo import DemoSource


def _hash_dir(root) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_same_seed_produces_byte_identical_output(isolated_env):
    DemoSource(isolated_env).materialise()
    first = _hash_dir(isolated_env.raw_dir)
    DemoSource(isolated_env).materialise()
    assert _hash_dir(isolated_env.raw_dir) == first


def test_different_seed_changes_output(isolated_env, monkeypatch):
    DemoSource(isolated_env).materialise()
    first = _hash_dir(isolated_env.raw_dir)
    monkeypatch.setenv("INGOMOB_SEED", "1234")
    from ingomob.config import load_settings
    DemoSource(load_settings()).materialise()
    assert _hash_dir(isolated_env.raw_dir) != first


def test_generator_injects_realistic_defects(isolated_env):
    """The demo data must contain gaps and zero runs, or it is too easy to model."""
    m = DemoSource(isolated_env).materialise()
    assert m["missing_pct"] > 0, "no missing hours - unrealistically clean"
    import pandas as pd
    t = pd.read_csv(isolated_env.raw_dir / "traffic_counts.csv")
    daytime = t[(t.hour >= 8) & (t.hour <= 18)]
    assert (daytime.vehicle_count == 0).sum() > 0, "no sensor faults present"
