"""IngoMobility command-line interface.

Every stage is a subcommand; ``run-all`` chains them. Global flags:
``--source demo|live``, ``--log-level``, ``--no-strict`` (do not abort on
data-quality failures). Exits with code 1 on a handled pipeline error and 2 on
a data-quality failure, so CI can distinguish them.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from .errors import DataQualityError, IngomobError
from .logging_conf import get_logger, setup_logging

log = get_logger(__name__)


def _settings():
    from .config import load_settings
    return load_settings()


# --------------------------------------------------------------------- stages
def cmd_generate(args):
    from .sources import build_source
    s = _settings()
    manifest = build_source(s).materialise()
    print(json.dumps(manifest, indent=2))


def cmd_validate(args):
    from .java_validate import run_validation
    run_validation(prefer_java=not args.python_only, strict=not args.no_strict,
                   settings=_settings())


def cmd_warehouse(args):
    from .transform import build_warehouse
    r = build_warehouse()
    print(f"warehouse: {len(r['objects'])} objects, "
          f"{sum(r['staging'].values()):,} staged rows")


def cmd_analytics(args):
    from .siting import recommend
    from .transit_quality import summarize
    s = _settings()
    summarize(s)
    recommend(settings=s)


def cmd_forecast(args):
    from .forecast import train_and_evaluate
    r = train_and_evaluate(_settings())
    summ = r["cv"]["summary"]
    print(f"CV MAE {summ['model']['mae']['mean']} ± {summ['model']['mae']['std']} "
          f"| calendar-only {summ['calendar_only']['mae']['mean']} "
          f"| seasonal-naive {summ['seasonal_naive']['mae']['mean']} "
          f"| lift {r['lift_over_calendar_only_pct']}%")


def cmd_dashboard(args):
    from .export_dashboard import build_dashboard_data
    from .plots import make_all
    s = _settings()
    d = build_dashboard_data(s)
    figs = make_all()
    print(f"dashboard: {d['bytes']:,} bytes, {len(figs)} figures")


def cmd_report(args):
    from .report import build_report
    print(build_report(_settings()))


def cmd_run_all(args):
    for step in (cmd_generate, cmd_validate, cmd_warehouse, cmd_analytics,
                 cmd_forecast, cmd_dashboard, cmd_report):
        step(args)
    log.info("pipeline complete")


def cmd_serve(args):
    """Serve the dashboard - cross-platform replacement for a shell script."""
    import functools
    import http.server
    import socketserver
    s = _settings()
    if not (s.dashboard_dir / "data.json").exists():
        log.warning("dashboard/data.json not found - run 'ingomob run-all' first")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(s.dashboard_dir))
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        print(f"Dashboard on http://localhost:{args.port}  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


def cmd_doctor(args):
    """Print the resolved environment - first thing to run when something breaks."""
    s = _settings()
    print("IngoMobility environment")
    print(f"  python            {sys.version.split()[0]} ({sys.platform})")
    print(f"  source mode       {s.source}")
    print(f"  data dir          {s.data_dir}")
    print(f"  warehouse         {s.db_path} {'[exists]' if s.db_path.exists() else '[missing]'}")
    print(f"  cache dir         {s.cache_dir}")
    print(f"  seed / sim days   {s.seed} / {s.sim_days}")
    print(f"  java (javac)      {shutil.which('javac') or 'not found -> Python DQ engine'}")
    for mod in ("duckdb", "pandas", "numpy", "sklearn", "matplotlib"):
        try:
            m = __import__(mod)
            print(f"  {mod:17s} {getattr(m, '__version__', '?')}")
        except ImportError:
            print(f"  {mod:17s} MISSING")
    raw = s.raw_dir
    n = len(list(raw.glob('**/*'))) if raw.exists() else 0
    print(f"  raw files         {n}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ingomob",
        description="Ingolstadt Open Mobility Intelligence pipeline",
        epilog="Environment variables are documented in docs/configuration.md")
    p.add_argument("--source", choices=("demo", "live"),
                   help="data source mode (overrides INGOMOB_SOURCE; default: demo)")
    p.add_argument("--log-level", default=None,
                   choices=("DEBUG", "INFO", "WARNING", "ERROR"),
                   help="logging verbosity (overrides INGOMOB_LOG_LEVEL)")
    p.add_argument("--no-strict", action="store_true",
                   help="do not abort the pipeline when data-quality rules fail")
    p.add_argument("--python-only", action="store_true",
                   help="skip the Java data-quality engine even if a JDK is present")
    sub = p.add_subparsers(dest="cmd", required=True)
    stages = [
        ("generate", cmd_generate, "materialise raw data for the selected source"),
        ("validate", cmd_validate, "run the data-quality gate"),
        ("warehouse", cmd_warehouse, "build the DuckDB star schema"),
        ("analytics", cmd_analytics, "transit quality + charging siting"),
        ("forecast", cmd_forecast, "train + cross-validate the demand model"),
        ("dashboard", cmd_dashboard, "export dashboard payload and figures"),
        ("report", cmd_report, "render the analysis report"),
        ("run-all", cmd_run_all, "run every stage in order"),
        ("doctor", cmd_doctor, "print the resolved environment and dependencies"),
    ]
    for name, fn, help_ in stages:
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(func=fn)
    sp = sub.add_parser("serve", help="serve the dashboard over HTTP")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.source:
        os.environ["INGOMOB_SOURCE"] = args.source
    setup_logging(args.log_level)
    try:
        args.func(args)
    except DataQualityError as exc:
        log.error("%s", exc)
        return 2
    except IngomobError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.warning("interrupted")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
