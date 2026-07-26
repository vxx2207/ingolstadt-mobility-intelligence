"""Logging setup. Level is configurable via INGOMOB_LOG_LEVEL (default INFO)."""
from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False
FORMAT = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"
DATEFMT = "%H:%M:%S"


def setup_logging(level: str | None = None) -> None:
    """Configure root logging once. Safe to call repeatedly."""
    global _CONFIGURED
    lvl = (level or os.environ.get("INGOMOB_LOG_LEVEL", "INFO")).upper()
    if _CONFIGURED:
        logging.getLogger().setLevel(lvl)
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(FORMAT, datefmt=DATEFMT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(lvl)
    logging.getLogger("matplotlib").setLevel("WARNING")
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
