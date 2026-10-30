"""Persistence for part categories and their template ownership."""

import sqlite3
from uuid import uuid4

from app.database import Database
from app.domain import PartCategoryCreate, PartCategoryRead, PartCategoryRename
from app.repositories.common import utc_now
from app.repositories.errors import RepositoryConflictError, RepositoryNotFoundError


class PartCategoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self) -> list[PartCategoryRead]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT c.*, COUNT(a.id) AS template_count
                   FROM part_categories c LEFT JOIN meshing_automations a ON a.category_id = c.id
                   GROUP BY c.id ORDER BY c.is_system DESC, c.name COLLATE NOCASE"""
            ).fetchall()
        return [PartCategoryRead(**dict(row)) for row in rows]

    def create(self, payload: PartCategoryCreate) -> PartCategoryRead:
        category_id = str(uuid4())
        now = utc_now()
        try:
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT INTO part_categories(id,name,description,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (category_id, payload.name, payload.description, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflictError(f"目录名称 {payload.name!r} 已存在。") from exc
        return self.get(category_id)

    def get(self, category_id: str) -> PartCategoryRead:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT c.*, COUNT(a.id) AS template_count
                   FROM part_categories c LEFT JOIN meshing_automations a ON a.category_id = c.id
                   WHERE c.id = ? GROUP BY c.id""",
                (category_id,),
            ).fetchone()
        if row is None:
            raise RepositoryNotFoundError(f"Part category {category_id!r} was not found.")
        return PartCategoryRead(**dict(row))

    def rename(self, category_id: str, payload: PartCategoryRename) -> PartCategoryRead:
        now = utc_now()
        try:
            with self.database.connect() as connection:
                row = connection.execute(
                    "SELECT is_system FROM part_categories WHERE id = ?", (category_id,)
                ).fetchone()
                if row is None:
                    raise RepositoryNotFoundError(f"Part category {category_id!r} was not found.")
                if row["is_system"]:
                    raise RepositoryConflictError("系统目录不能重命名。")
                connection.execute(
                    "UPDATE part_categories SET name = ?, updated_at = ? WHERE id = ?",
                    (payload.name, now, category_id),
                )
                connection.execute(
                    """UPDATE meshing_automations SET model_family = ?, updated_at = ?
                       WHERE category_id = ?""",
                    (payload.name, now, category_id),
                )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflictError(f"目录名称 {payload.name!r} 已存在。") from exc
        return self.get(category_id)

    def delete(self, category_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT is_system FROM part_categories WHERE id = ?", (category_id,)
            ).fetchone()
            if row is None:
                raise RepositoryNotFoundError(f"Part category {category_id!r} was not found.")
            if row["is_system"]:
                raise RepositoryConflictError("系统目录不能删除。")
            count = connection.execute(
                "SELECT COUNT(*) FROM meshing_automations WHERE category_id = ?", (category_id,)
            ).fetchone()[0]
            if count:
                raise RepositoryConflictError("请先将目录中的模板移走或删除，再删除目录。")
            connection.execute("DELETE FROM part_categories WHERE id = ?", (category_id,))
