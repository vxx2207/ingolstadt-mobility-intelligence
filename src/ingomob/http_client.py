"""Small, dependency-free HTTP client for the ``live`` source mode.

Features that matter in production and are usually missing from portfolio code:
retries with exponential backoff, explicit timeouts, an on-disk cache keyed by
URL hash, SHA-256 recording for provenance, and errors that say what to do next.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .errors import DownloadError
from .logging_conf import get_logger

log = get_logger(__name__)

USER_AGENT = "ingomob/2.0 (open-data portfolio pipeline; +https://github.com/)"


def _cache_path(cache_dir: Path, url: str, suffix: str) -> Path:
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    return cache_dir / f"{key}{suffix}"


def fetch(url: str, cache_dir: Path, *, timeout: int = 30, retries: int = 3,
          suffix: str = ".bin", force: bool = False) -> Path:
    """Download ``url`` into ``cache_dir`` and return the local path.

    Cached files are reused unless ``force`` is set. Raises :class:`DownloadError`
    with an actionable hint after ``retries`` failed attempts.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = _cache_path(cache_dir, url, suffix)
    meta = dest.with_suffix(dest.suffix + ".meta.json")
    if dest.exists() and not force:
        log.info("cache hit  %s (%s bytes)", dest.name, dest.stat().st_size)
        return dest

    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            log.info("GET %s (attempt %d/%d)", url, attempt, retries)
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
                status = getattr(resp, "status", 200)
            if not payload:
                raise DownloadError(f"Empty response body from {url}")
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(payload)
            tmp.replace(dest)
            digest = hashlib.sha256(payload).hexdigest()
            meta.write_text(json.dumps({
                "url": url, "status": status, "bytes": len(payload),
                "sha256": digest, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, indent=2), encoding="utf-8")
            log.info("saved %s (%d bytes, sha256=%s…)", dest.name, len(payload), digest[:12])
            return dest
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, DownloadError) as exc:
            last = exc
            log.warning("attempt %d failed: %s", attempt, exc)
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))

    raise DownloadError(f"Could not download {url} after {retries} attempts: {last}")


def provenance(cache_dir: Path) -> list[dict]:
    """Return the recorded metadata of every cached download (for the report)."""
    out = []
    for m in sorted(cache_dir.glob("*.meta.json")):
        try:
            out.append(json.loads(m.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out
