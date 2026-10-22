"""Background job query endpoints."""

from fastapi import APIRouter, status

from app.api.deps import DatabaseDependency
from app.domain import JobCreate, JobRead
from app.repositories.jobs import JobRepository

router = APIRouter(tags=["jobs"])


@router.get("", response_model=list[JobRead])
def list_jobs(database: DatabaseDependency, limit: int = 50) -> list[JobRead]:
    return JobRepository(database).list(limit=max(1, min(limit, 200)))


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, database: DatabaseDependency) -> JobRead:
    return JobRepository(database).create(payload)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, database: DatabaseDependency) -> JobRead:
    return JobRepository(database).get(job_id)


@router.post("/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: str, database: DatabaseDependency) -> JobRead:
    return JobRepository(database).cancel(job_id)
