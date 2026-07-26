"""Engine dispatcher for the data-quality gate.

Prefers the Java validator (the path CI exercises, and the reason this project
is polyglot); falls back to the Python engine in :mod:`ingomob.quality` when no
JDK is present. Both implement the same rule specification.
"""
from __future__ import annotations

import json
import shutil
import subprocess

from . import quality
from .config import Settings, load_settings
from .logging_conf import get_logger

log = get_logger(__name__)


def _java_available() -> bool:
    return bool(shutil.which("javac") and shutil.which("java"))


def _run_java(s: Settings) -> dict:
    out_dir = s.java_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    srcs = sorted((s.java_dir / "src/com/ingomob/dq").glob("*.java"))
    report_path = s.processed_dir / "data_quality_report.json"
    subprocess.run(["javac", "-d", str(out_dir), *map(str, srcs)],
                   check=True, capture_output=True, text=True)
    subprocess.run(["java", "-cp", str(out_dir), "com.ingomob.dq.DataQualityValidatorTest"],
                   check=True, capture_output=True, text=True)
    proc = subprocess.run(["java", "-cp", str(out_dir), "com.ingomob.dq.DataQualityValidator",
                           str(s.raw_dir), str(report_path)], capture_output=True, text=True)
    if proc.returncode not in (0, 2):        # 2 = rules failed, still writes a report
        raise RuntimeError(proc.stderr.strip() or "java validator crashed")
    report = json.loads(report_path.read_text())
    report["engine"] = "java"
    return report


def run_validation(prefer_java: bool = True, strict: bool = True,
                   settings: Settings | None = None) -> dict:
    s = settings or load_settings()
    s.processed_dir.mkdir(parents=True, exist_ok=True)
    report = None
    if prefer_java and _java_available():
        try:
            report = _run_java(s)
        except (subprocess.CalledProcessError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            log.warning("Java validator unavailable (%s); using Python engine", exc)
    if report is None:
        report = quality.evaluate(s)
    quality.write_report(report, s)
    log.info("data quality: engine=%s rows=%s all_passed=%s", report["engine"],
             f"{report['total_rows_checked']:,}", report["all_passed"])
    if strict:
        quality.enforce(report)
    return report
