"""Application settings persistence."""

from app.database import Database
from app.repositories.common import utc_now


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_all(self) -> dict[str, str]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT key, value FROM app_settings ORDER BY key").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def update(self, values: dict[str, str]) -> dict[str, str]:
        now = utc_now()
        with self.database.connect() as connection:
            for key, value in values.items():
                connection.execute(
                    """
                    INSERT INTO app_settings(key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE
                    SET value = excluded.value, updated_at = excluded.updated_at
                    """,
                    (key, value, now),
                )
        return self.get_all()
