"""Cooperative job cancellation helpers."""

from app.repositories.jobs import JobRepository


class JobCancelledError(RuntimeError):
    """Raised when a persisted job has been cancelled by the user."""


def ensure_job_active(jobs: JobRepository, job_id: str) -> None:
    if jobs.is_cancelled(job_id):
        raise JobCancelledError("Cancelled by user.")
