"""Migration verification must work outside the developer virtualenv layout."""

from scripts import verify_migrations


def test_alembic_runs_without_a_repository_local_virtualenv(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_migrations, "ROOT", tmp_path)
    env = verify_migrations._migration_env(
        f"sqlite+pysqlite:///{tmp_path / 'unused.db'}"
    )
    verify_migrations._alembic(env, "--version")
