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

    assert migration_count == 12
    assert {
        "schema_migrations",
        "automations",
        "models",
        "model_automations",
        "app_settings",
        "jobs",
        "sync_logs",
        "meshing_automations",
        "part_categories",
        "meshing_template_revisions",
        "meshing_tasks",
        "meshing_task_artifacts",
        "meshing_task_events",
        "agent_runs",
        "agent_run_events",
        "agent_knowledge_sources",
        "agent_category_knowledge",
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
    assert latest == 12
    assert table is not None


def test_venturi_templates_move_to_matching_category_on_upgrade(tmp_path: Path) -> None:
    database = Database(tmp_path / "venturi-upgrade.db")
    with database.connect() as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
    for version, sql in MIGRATIONS[:7]:
        with database.connect() as connection:
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 'test')",
                (version,),
            )
    with database.connect() as connection:
        preset = (
            '{"schema_version":1,"fluent_version":"25.2","workflow_type":"watertight","items":[]}'
        )
        for name, family in [
            ("localsize", ""),
            ("Venturi boundary", "文丘里"),
            ("Venturi sizing", "文丘里"),
            ("Venturi pipe", "文丘里管"),
        ]:
            connection.execute(
                """INSERT INTO meshing_automations(
                    name, model_family, workflow_type, preset_json, status,
                    created_at, updated_at, category_id
                ) VALUES (?, ?, 'watertight', ?, 'draft', 'now', 'now', 'uncategorized')""",
                (name, family, preset),
            )

    database.initialize()

    with database.connect() as connection:
        rows = connection.execute(
            """SELECT a.model_family, c.name AS category_name
               FROM meshing_automations a JOIN part_categories c ON c.id=a.category_id
               ORDER BY a.id"""
        ).fetchall()
        knowledge_links = connection.execute(
            """SELECT c.name, s.id FROM agent_category_knowledge link
               JOIN part_categories c ON c.id = link.category_id
               JOIN agent_knowledge_sources s ON s.id = link.knowledge_source_id
               ORDER BY c.name"""
        ).fetchall()
    assert [(row["model_family"], row["category_name"]) for row in rows] == [
        ("文丘里", "文丘里"),
        ("文丘里", "文丘里"),
        ("文丘里", "文丘里"),
        ("文丘里管", "文丘里管"),
    ]
    assert [(row["name"], row["id"]) for row in knowledge_links] == [
        ("文丘里", "venturi-boundary-layer-v2"),
        ("文丘里管", "venturi-boundary-layer-v2"),
    ]


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
