# Attachment contract

The local implementation accepts PDF, PNG, JPEG, TXT, CSV, and JSON files.
The filename extension and browser-declared MIME type must agree. The API reads
up to 5 MiB plus one byte, so request metadata cannot bypass the size limit;
there are at most five attachments per comment.

Bytes are stored under a generated UUID key in the Docker `attachments` volume.
The original filename is metadata for download display only. A soft-deleted
comment makes its attachments inaccessible. If metadata persistence fails after
the blob is written, the storage adapter removes that generated blob. A future
production cleanup job should scan for any old unreferenced keys before moving
to object storage.

OpenRouter receives a ticket text snapshot only; attachment bytes are not sent
to the analyzer.
