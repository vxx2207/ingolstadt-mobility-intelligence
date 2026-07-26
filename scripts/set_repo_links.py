#!/usr/bin/env python3
"""Replace the ``YOUR_GITHUB_USER`` placeholder across the repository.

The GitHub handle is deliberately not hard-coded anywhere: a portfolio repo that
ships someone else's username (or a broken CI badge) looks careless. Run once
after forking:

    python scripts/set_repo_links.py my-github-name
"""
from __future__ import annotations

import sys
from pathlib import Path

PLACEHOLDER = "YOUR_GITHUB_USER"
ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("*.md", "docs/*.md", ".github/workflows/*.yml")

# Only substitute inside real links. An earlier version replaced every
# occurrence, which also rewrote the prose *explaining* the placeholder
# ("single `YOUR_GITHUB_USER` placeholder" became a self-contradiction).
LINK_PATTERNS = (
    "github.com/{}",
    "{}.github.io",
)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1].startswith("-"):
        print(__doc__)
        return 1
    user = argv[1].strip().lstrip("@")
    changed = []
    for pattern in TARGETS:
        for path in ROOT.glob(pattern):
            text = path.read_text(encoding="utf-8")
            updated = text
            for tpl in LINK_PATTERNS:
                updated = updated.replace(tpl.format(PLACEHOLDER), tpl.format(user))
            if updated != text:
                path.write_text(updated, encoding="utf-8")
                changed.append(path.relative_to(ROOT))
    if not changed:
        print(f"No occurrences of {PLACEHOLDER} found - already configured?")
        return 0
    print(f"Set GitHub user to '{user}' in {len(changed)} file(s):")
    for c in changed:
        print(f"  - {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
