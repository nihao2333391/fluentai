"""Recent-session restoration endpoint."""

from fastapi import APIRouter

from app.api.deps import DatabaseDependency
from app.domain import RecentSessionRead
from app.repositories.automations import AutomationRepository
from app.repositories.errors import RepositoryNotFoundError
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.repositories.models import ModelRepository
from app.repositories.settings import SettingsRepository

router = APIRouter(tags=["session"])


def _positive_id(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


@router.get("/recent", response_model=RecentSessionRead)
def get_recent_session(database: DatabaseDependency) -> RecentSessionRead:
    values = SettingsRepository(database).get_all()
    model_id = _positive_id(values.get("recent_model_id"))
    automation_id = _positive_id(values.get("recent_automation_id"))
    meshing_automation_id = _positive_id(values.get("recent_meshing_automation_id"))

    model = None
    automation = None
    meshing_automation = None
    if model_id is not None:
        try:
            model = ModelRepository(database).get(model_id)
        except RepositoryNotFoundError:
            model = None
    if automation_id is not None:
        try:
            automation = AutomationRepository(database).get(automation_id)
        except RepositoryNotFoundError:
            automation = None
    if meshing_automation_id is not None:
        try:
            meshing_automation = MeshingAutomationRepository(database).get(meshing_automation_id)
        except RepositoryNotFoundError:
            meshing_automation = None

    return RecentSessionRead(
        model=model,
        automation=automation,
        meshing_automation=meshing_automation,
        updated_at=values.get("recent_session_at"),
    )
