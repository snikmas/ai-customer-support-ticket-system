# Attachment contract

The local implementation accepts PDF, PNG, JPEG, TXT, CSV, and JSON files.
The filename extension and browser-declared MIME type must agree. The API reads
up to 5 MiB plus one byte, so request metadata cannot bypass the size limit;
there are at most five attachments per comment.

Bytes are stored under a generated UUID key in the Docker `attachments` volume.
The original filename is metadata for download display only and is never used as a
filesystem path. A soft-deleted comment makes its attachments inaccessible, and
generated keys reject path traversal.

## Upload path and concurrency

A request validates the filename/type and spools the body before any database
lock is taken, then a worker thread performs the blocking authorization, storage,
and SQL work so the async event loop is not stalled. The cap, the authorization
re-check, and the counter update share one transaction:

- PostgreSQL locks the comment row with `SELECT ... FOR UPDATE`.
- SQLite takes its single-writer `BEGIN IMMEDIATE` lock first.

Two uploads at four existing files therefore cannot both commit; the loser gets
`attachment_count_exceeded`. The comment's `attachments_count` is incremented
with an atomic `UPDATE ... SET attachments_count = attachments_count + 1`, so
concurrent increments are not lost. Deletion and visibility changes are
re-checked against the locked rows, so a comment deleted or restricted after the
initial read cannot receive a new file.

## Cleanup semantics

The blob is written before the metadata transaction. If the write fails, or if
the metadata insert/commit fails (including a rejected cap or a failed re-check),
the unreferenced generated blob is removed. Bytes committed for an existing
attachment are never deleted. A process interruption between the write and the
commit can leave an orphan blob; that is recoverable, not corruption.

`scripts/cleanup_attachments.py` reports orphan candidates and is a **dry run by
default**. It is bounded (`--limit`), ignores keys younger than
`--min-age-hours` (default 24) to protect in-flight uploads, only considers
generated-key names, and never deletes a key referenced by any committed
attachment row (including soft-deleted rows). Pass `--apply` to delete.

OpenRouter receives a ticket text snapshot only; attachment bytes are not sent
to the analyzer.
