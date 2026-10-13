"""Phase F tests for the dry-run-by-default orphan attachment cleanup command."""

import os
import sys
import time

import pytest
from sqlalchemy import create_engine, event

from scripts.cleanup_attachments import find_orphans, main
from src.db import models as db_models, operations
from src.storage import LocalAttachmentStorage

OLD = 48 * 3600
KEY = "a" * 32 + ".pdf"
OTHER = "b" * 32 + ".txt"


def _storage(tmp_path):
    return LocalAttachmentStorage(tmp_path / "uploads")


def _write(storage, key, age_seconds=OLD):
    path = storage.root / key
    path.write_bytes(b"orphan")
    modified = time.time() - age_seconds
    os.utime(path, (modified, modified))
    return path


def test_find_orphans_excludes_referenced_and_non_generated(tmp_path):
    storage = _storage(tmp_path)
    referenced = _write(storage, KEY, age_seconds=OLD)
    _write(storage, OTHER, age_seconds=OLD)
    (storage.root / "notes.txt").write_text("user filename")

    orphans = find_orphans(storage, {KEY}, min_age_seconds=24 * 3600, limit=100)

    assert orphans == [OTHER]
    assert referenced.exists()


def test_find_orphans_honours_age_threshold(tmp_path):
    storage = _storage(tmp_path)
    _write(storage, KEY, age_seconds=OLD)
    fresh = _write(storage, OTHER, age_seconds=10)

    orphans = find_orphans(storage, set(), min_age_seconds=24 * 3600, limit=100)

    assert orphans == [KEY]
    assert fresh.exists()


def test_find_orphans_is_bounded_and_oldest_first(tmp_path):
    storage = _storage(tmp_path)
    keys = [f"{i:032x}.pdf" for i in range(1, 6)]
    for index, key in enumerate(keys):
        _write(storage, key, age_seconds=OLD + index)

    orphans = find_orphans(storage, set(), min_age_seconds=3600, limit=2)

    # Largest age means oldest mtime, which sorts first.
    assert orphans == [keys[4], keys[3]]


def test_find_orphans_rejects_non_positive_limit(tmp_path):
    storage = _storage(tmp_path)
    with pytest.raises(ValueError):
        find_orphans(storage, set(), min_age_seconds=0, limit=0)


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'cleanup.db'}",
        connect_args={"timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    db_models.Base.metadata.create_all(engine)
    return engine


def test_cleanup_dry_run_does_not_delete(monkeypatch, tmp_path, capsys):
    engine = _engine(tmp_path)
    monkeypatch.setattr(operations, "engine", engine)
    storage_root = tmp_path / "uploads"
    storage_root.mkdir()
    orphan = storage_root / KEY
    orphan.write_bytes(b"x")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanup_attachments.py",
            "--attachments-dir",
            str(storage_root),
            "--min-age-hours",
            "0",
        ],
    )
    assert main() == 0
    assert orphan.exists()
    assert "dry-run" in capsys.readouterr().out.lower()
    engine.dispose()


def test_cleanup_apply_removes_only_orphans(monkeypatch, tmp_path):
    engine = _engine(tmp_path)
    referenced_key = "c" * 32 + ".pdf"
    monkeypatch.setattr(operations, "engine", engine)
    monkeypatch.setattr(
        operations,
        "get_all_attachment_storage_keys",
        lambda: {referenced_key},
    )
    storage_root = tmp_path / "uploads"
    storage_root.mkdir()
    orphan = storage_root / KEY
    referenced = storage_root / referenced_key
    orphan.write_bytes(b"x")
    referenced.write_bytes(b"x")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanup_attachments.py",
            "--apply",
            "--attachments-dir",
            str(storage_root),
            "--min-age-hours",
            "0",
        ],
    )
    assert main() == 0
    assert not orphan.exists()
    assert referenced.exists()

    storage = LocalAttachmentStorage(storage_root)
    assert storage.generated_keys() == [referenced.name]
    engine.dispose()
