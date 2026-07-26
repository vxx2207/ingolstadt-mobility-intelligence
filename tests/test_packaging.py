"""Packaging consistency.

Regression guard: `constraints.txt` pinned pyarrow==25.0.0 while
`requirements.txt` demanded pyarrow<25.0, so the documented reproducible
install (`pip install -r requirements-dev.txt -c constraints.txt`) was
impossible. CI installs without constraints, so nothing caught it.
"""
from __future__ import annotations

import re

from ingomob.config import PROJECT_ROOT


def _version(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


def _requirements() -> dict[str, str]:
    out = {}
    for name in ("requirements.txt", "requirements-dev.txt"):
        for line in (PROJECT_ROOT / name).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-r")):
                continue
            m = re.match(r"([A-Za-z0-9_.\-]+)(.*)", line)
            out[m.group(1).lower()] = m.group(2)
    return out


def _constraints() -> dict[str, str]:
    out = {}
    for line in (PROJECT_ROOT / "constraints.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, ver = line.split("==")
        out[name.strip().lower()] = ver.strip()
    return out


def test_pins_satisfy_declared_ranges():
    reqs, cons = _requirements(), _constraints()
    problems = []
    for pkg, pin in cons.items():
        rng = reqs.get(pkg)
        if not rng:
            continue          # transitive dependency, no declared range
        upper = re.search(r"<\s*([0-9.]+)", rng)
        lower = re.search(r">=\s*([0-9.]+)", rng)
        if upper and _version(pin) >= _version(upper.group(1)):
            problems.append(f"{pkg}: pinned {pin} violates upper bound {rng}")
        if lower and _version(pin) < _version(lower.group(1)):
            problems.append(f"{pkg}: pinned {pin} violates lower bound {rng}")
    assert not problems, "constraints.txt contradicts requirements: " + "; ".join(problems)


def test_pyproject_and_requirements_agree():
    text = (PROJECT_ROOT / "pyproject.toml").read_text()
    block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    declared = dict(
        (m.group(1).lower(), m.group(2))
        for m in (re.match(r'\s*"([A-Za-z0-9_.\-]+)(.*)"', ln)
                  for ln in block.splitlines() if ln.strip().startswith('"'))
        if m
    )
    reqs = _requirements()
    for pkg, spec in declared.items():
        assert pkg in reqs, f"{pkg} in pyproject but missing from requirements.txt"
        assert spec.strip(" ,") == reqs[pkg].strip(" ,"), (
            f"{pkg}: pyproject says '{spec}', requirements.txt says '{reqs[pkg]}'")
