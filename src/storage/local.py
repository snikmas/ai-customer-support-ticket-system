from pathlib import Path
import re

# Keys are generated as 32 lowercase hex characters (`uuid4().hex`) plus one
# allowed extension. User-supplied filenames never become storage keys, so a
# cleanup command can safely restrict itself to names matching this shape.
GENERATED_STORAGE_KEY = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,8}$")


class LocalAttachmentStorage:
    """Small replaceable storage adapter for the local Docker demo."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if path.parent != self.root or path == self.root:
            raise ValueError("invalid_attachment_storage_key")
        return path

    def save(self, storage_key: str, content: bytes) -> Path:
        path = self._path(storage_key)
        path.write_bytes(content)
        return path

    def path(self, storage_key: str) -> Path:
        path = self._path(storage_key)
        if not path.is_file():
            raise FileNotFoundError(storage_key)
        return path

    def delete(self, storage_key: str) -> None:
        path = self._path(storage_key)
        if path.exists():
            path.unlink()

    def generated_keys(self) -> list[str]:
        """List direct children whose names match the generated-key shape."""
        if not self.root.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self.root.iterdir()
            if entry.is_file() and GENERATED_STORAGE_KEY.match(entry.name)
        )

    def modified_at(self, storage_key: str) -> float:
        """Return the mtime of a generated key, or raise if it is absent."""
        return self._path(storage_key).stat().st_mtime
