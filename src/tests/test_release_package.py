"""Verify the documented entry point from the delivered source archive."""

import hashlib
import subprocess
import tarfile

from scripts.build_release import VERSION, build


def test_release_contains_a_working_launcher_and_setup_files(tmp_path):
    archive = build(tmp_path / "release")
    prefix = f"resolveai-v{VERSION}"
    with tarfile.open(archive) as snapshot:
        members = snapshot.getmembers()
        names = [member.name for member in members]
        assert len(names) == len(set(names)), "Archive members must be unique"
        for relative in (
            "project.sh", ".env.example", "site/.env.example", "site/README.md",
        ):
            assert f"{prefix}/{relative}" in names
        assert all(
            not {"notes", ".project-workflow", "keys", ".env"}.intersection(
                member.name.split("/")
            )
            for member in members
        )
        manifest = snapshot.extractfile(f"{prefix}/MANIFEST.sha256").read().decode()
        launcher_member = snapshot.getmember(f"{prefix}/project.sh")
        launcher_bytes = snapshot.extractfile(launcher_member).read()
        assert f"{hashlib.sha256(launcher_bytes).hexdigest()}  project.sh" in manifest
        assert launcher_member.mode & 0o111, "The documented launcher must be executable"

    launcher = tmp_path / "project.sh"
    launcher.write_bytes(launcher_bytes)
    launcher.chmod(launcher_member.mode)
    result = subprocess.run(
        [str(launcher), "--help"], capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 0
    assert "Usage: ./project.sh" in result.stdout
