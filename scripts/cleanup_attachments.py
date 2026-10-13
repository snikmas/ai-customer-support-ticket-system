"""Delete or preview removal of orphaned local attachment blobs.

An orphan is a generated storage key with no corresponding ``attachments`` row.
The command is DRY-RUN BY DEFAULT: it only reports candidates unless ``--apply``
is passed. It is bounded by ``--limit`` and ignores any key younger than
``--min-age-hours`` so an in-flight upload (bytes written, metadata not yet
committed) is never treated as abandoned.

Safety rules:
- Only names matching the generated-key shape are considered. The storage
  adapter's ``generated_keys`` never returns user filenames.
- A key referenced by ANY committed attachment row (including soft-deleted
  rows) is never deleted.
- The default scan never deletes anything.
"""

from __future__ import annotations

import argparse
import time

from src.core.config import ATTACHMENTS_DIR
from src.db import operations
from src.storage import LocalAttachmentStorage


def find_orphans(
    storage: LocalAttachmentStorage,
    referenced: set[str],
    *,
    min_age_seconds: float,
    limit: int,
    now: float | None = None,
) -> list[str]:
    """Return up to ``limit`` oldest orphan keys older than the threshold."""
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    cutoff = (time.time() if now is None else now) - min_age_seconds
    candidates: list[tuple[float, str]] = []
    for key in storage.generated_keys():
        if key in referenced:
            continue
        try:
            modified = storage.modified_at(key)
        except OSError:
            continue
        if modified > cutoff:
            continue
        candidates.append((modified, key))
    candidates.sort()
    return [key for _, key in candidates[:limit]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the reported orphan blobs. Without this flag the run is a dry run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of orphan blobs to report or remove (default: 100).",
    )
    parser.add_argument(
        "--min-age-hours",
        type=float,
        default=24.0,
        help="Only consider blobs older than this many hours (default: 24).",
    )
    parser.add_argument(
        "--attachments-dir",
        default=str(ATTACHMENTS_DIR),
        help="Attachment storage root (defaults to the configured ATTACHMENTS_DIR).",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit must be greater than zero")
    if args.min_age_hours < 0:
        parser.error("--min-age-hours must not be negative")

    storage = LocalAttachmentStorage(args.attachments_dir)
    referenced = operations.get_all_attachment_storage_keys()
    orphans = find_orphans(
        storage,
        referenced,
        min_age_seconds=args.min_age_hours * 3600,
        limit=args.limit,
    )

    mode = "apply" if args.apply else "dry-run"
    print(f"[{mode}] {len(orphans)} orphan candidate(s) in {storage.root}")
    for key in orphans:
        print(f"  {key}")
    if not args.apply:
        print("Dry run: no files removed. Re-run with --apply to delete these keys.")
        return 0

    removed = 0
    for key in orphans:
        if key in referenced:
            raise RuntimeError(f"refusing to delete referenced key {key}")
        storage.delete(key)
        removed += 1
    print(f"Removed {removed} orphan blob(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
