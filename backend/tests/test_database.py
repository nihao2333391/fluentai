from pathlib import Path

from app.database import Database


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

    assert migration_count == 1
    assert {
        "schema_migrations",
        "automations",
        "models",
        "model_automations",
        "app_settings",
        "jobs",
        "sync_logs",
    }.issubset(table_names)
    assert {str(row["key"]): str(row["value"]) for row in settings}["language"] == "zh"
