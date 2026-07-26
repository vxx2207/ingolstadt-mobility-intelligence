"""Typed error hierarchy.

Every failure mode the pipeline can hit gets a specific class with an
actionable message, so users see *what to do* instead of a stack trace.
"""
from __future__ import annotations


class IngomobError(Exception):
    """Base class for all pipeline errors."""

    hint: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        base = super().__str__()
        return f"{base}\n  → {self.hint}" if self.hint else base


class ConfigError(IngomobError):
    hint = "Check your INGOMOB_* environment variables (see docs/configuration.md)."


class SourceError(IngomobError):
    """Raised when raw data cannot be obtained."""

    hint = "Run 'ingomob generate --source demo' for the offline dataset."


class DownloadError(SourceError):
    hint = ("The live source could not be downloaded. Check internet access, or fall back to "
            "'--source demo'. Set INGOMOB_HTTP_TIMEOUT / INGOMOB_HTTP_RETRIES to tune.")


class SchemaError(IngomobError):
    """Raised when input data does not match the declared contract."""

    hint = "The input file does not match the expected schema (see src/ingomob/schemas.py)."


class DataQualityError(IngomobError):
    """Raised when the data-quality gate fails."""

    hint = "Inspect data/processed/data_quality_report.json for the failing rules."


class WarehouseError(IngomobError):
    hint = "Re-run 'ingomob warehouse'. Delete data/warehouse/*.duckdb if the file is corrupt."


class NotBuiltError(IngomobError):
    """Raised when a stage runs before its prerequisite."""

    hint = "Run the stages in order, or simply run 'ingomob run-all'."
