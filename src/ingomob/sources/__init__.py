"""Interchangeable data sources.

``demo``  - deterministic synthetic data, offline, used by default and in CI.
``live``  - real downloads from official open-data endpoints.

Both emit the *same* files in the same schemas (see ``ingomob.schemas``), so
every downstream stage is source-agnostic.
"""
from __future__ import annotations

from ..config import Settings
from ..errors import ConfigError


def build_source(settings: Settings):
    if settings.source == "demo":
        from .demo import DemoSource
        return DemoSource(settings)
    if settings.source == "live":
        from .live import LiveSource
        return LiveSource(settings)
    raise ConfigError(f"Unknown source {settings.source!r}")
