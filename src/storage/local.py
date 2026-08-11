from pathlib import Path


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
