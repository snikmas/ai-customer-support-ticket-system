"""Explicit release source allowlist for the ResolveAI v1 snapshot.

Everything shipped is enumerated here; anything not listed is excluded by
default. The snapshot deliberately omits internal plans, local review evidence,
personal notes, databases, uploaded files, secret files, signing keys, caches,
build output, and unrelated work.

``main()`` prints the resolved file list (one path per line) so packaging and
manifest steps share exactly one definition of "the release source".
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Top-level build, dependency, and configuration files.
EXACT_FILES = (
    "main.py",
    "bootstrap_superadmin.py",
    "alembic.ini",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "Dockerfile",
    ".dockerignore",
    "compose.yaml",
    "compose.smoke.yaml",
    "project.sh",
    ".env.example",
    "README.md",
    ".github/workflows/ci.yml",
    "site/Dockerfile",
    "site/README.md",
    "site/.env.example",
    "site/package.json",
    "site/package-lock.json",
    "site/index.html",
    "site/vite.config.ts",
    "site/vitest.config.ts",
    "site/tsconfig.json",
    "site/tsconfig.app.json",
    "site/tsconfig.node.json",
    "site/nginx.conf",
)

# Curated public docs. Internal folders (docs/archive, docs/audit) and personal
# files (docs/astra_info.md, docs/media) are intentionally not shipped.
EXACT_FILES += tuple(
    f"docs/{name}.md"
    for name in (
        "ACCEPTANCE",
        "AI_EVALUATION",
        "API_EXAMPLES",
        "ARCHITECTURE",
        "ATTACHMENTS",
        "INTERVIEW_CHECK",
        "INTERVIEW_DEMO",
        "OPERATIONS",
        "PERMISSIONS",
        "RELIABILITY",
        "TICKET_WORKFLOW",
    )
)

# Source trees included in full (filtered by exclusions below).
GLOB_PATTERNS = (
    "src/**/*.py",
    "alembic/**/*.py",
    "alembic/**/*.mako",
    "scripts/**/*.py",
    "site/src/**/*",
    "site/public/**/*",
)

EXCLUDED_DIR_PARTS = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        ".git",
    }
)
EXCLUDED_FILE_NAMES = frozenset({".env", ".DS_Store"})
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo", ".tsbuildinfo", ".log"})


def _is_excluded(relative: Path) -> bool:
    if set(relative.parts) & EXCLUDED_DIR_PARTS:
        return True
    if relative.name in EXCLUDED_FILE_NAMES:
        return True
    if relative.suffix in EXCLUDED_SUFFIXES:
        return True
    # scripts/ nginx smoke keys and anything under a keys/ directory.
    if "keys" in relative.parts:
        return True
    return False


def release_files() -> list[Path]:
    """Return the sorted, repo-relative release source files that exist."""
    found: set[Path] = set()
    for relative in EXACT_FILES:
        candidate = ROOT / relative
        if candidate.is_file() and not _is_excluded(Path(relative)):
            found.add(Path(relative))
    for pattern in GLOB_PATTERNS:
        for candidate in ROOT.glob(pattern):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(ROOT)
            if not _is_excluded(relative):
                found.add(relative)
    return sorted(found)


def main() -> int:
    for relative in release_files():
        print(relative.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
