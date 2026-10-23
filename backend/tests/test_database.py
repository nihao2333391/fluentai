from pathlib import Path

from app.database import MIGRATIONS, Database


def test_migrations_create_schema_and_are_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "fluent-ai.db")

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        migration_count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        table_names = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        settings = connection.execute("SELECT key, value FROM app_settings ORDER BY key").fetchall()

    assert migration_count == 3
    assert {
        "schema_migrations",
        "automations",
        "models",
        "model_automations",
        "app_settings",
        "jobs",
        "sync_logs",
        "meshing_automations",
    }.issubset(table_names)
    assert {str(row["key"]): str(row["value"]) for row in settings}["language"] == "zh"


def test_migration_upgrade_from_v1_adds_meshing_table(tmp_path: Path) -> None:
    database = Database(tmp_path / "upgrade.db")
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.executescript(MIGRATIONS[0][1])
        connection.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (1, 'test')")

    database.initialize()

    with database.connect() as connection:
        latest = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meshing_automations'"
        ).fetchone()
    assert latest == 3
    assert table is not None


def test_database_backup_and_restore(tmp_path: Path) -> None:
    database = Database(tmp_path / "backup.db")
    database.initialize()
    with database.connect() as connection:
        connection.execute("UPDATE app_settings SET value = 'before' WHERE key = 'language'")
    backup = database.create_backup("test")
    backup_size = backup["size"]
    assert isinstance(backup_size, int) and backup_size > 0
    with database.connect() as connection:
        connection.execute("UPDATE app_settings SET value = 'after' WHERE key = 'language'")
    safety, _restored = database.restore_backup(str(backup["name"]))
    assert safety["name"] != backup["name"]
    with database.connect() as connection:
        value = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'language'"
        ).fetchone()[0]
    assert value == "before"
    assert len(database.list_backups()) >= 2
