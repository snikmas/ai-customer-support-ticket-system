"""Build the ResolveAI v1 local source snapshot from the release allowlist.

The snapshot contains exactly ``scripts/release_allowlist.py`` files plus a
generated ``VERSION`` and ``MANIFEST.sha256``. Internal plans, local evidence,
notes, databases, uploads, secrets, keys, caches, and build output are excluded
by construction. The result is a versioned ``.tar.gz`` with a printed checksum.

Usage:
    myvenv/bin/python scripts/build_release.py [--output-dir DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.release_allowlist import release_files  # noqa: E402

VERSION = "1.0.0-local"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(output_dir: Path) -> Path:
    files = release_files()
    if not files:
        raise SystemExit("release allowlist resolved no files")

    output_dir.mkdir(parents=True, exist_ok=True)
    package_name = f"resolveai-v{VERSION}"
    staging = output_dir / package_name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for relative in files:
        source = ROOT / relative
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    (staging / "VERSION").write_text(
        f"{VERSION}\n", encoding="utf-8"
    )

    manifest_lines = []
    for relative in sorted(p for p in files):
        digest = _sha256(staging / relative)
        manifest_lines.append(f"{digest}  {relative.as_posix()}")
    (staging / "MANIFEST.sha256").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8"
    )

    archive = output_dir / f"{package_name}.tar.gz"
    # Deterministic-ish archive: sorted members, fixed mtime for the top dir.
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(staging.rglob("*")):
            tar.add(path, arcname=path.relative_to(output_dir))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / ".project-workflow" / "release"),
    )
    args = parser.parse_args()

    archive = build(Path(args.output_dir))
    digest = _sha256(archive)
    stamp = datetime.now(timezone.utc).isoformat()
    (archive.parent / f"{archive.stem}.sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    print(f"version: {VERSION}")
    print(f"files:   {len(release_files())}")
    print(f"archive: {archive}")
    print(f"sha256:  {digest}")
    print(f"built:   {stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
