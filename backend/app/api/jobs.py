"""Durable job API with status, retry, cancellation and event history."""
from fastapi import APIRouter, HTTPException
from app.config import settings
from app.services.jobs import JobRepository

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
jobs = JobRepository(settings.data_dir)


def _get(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}")
async def get_job(job_id: str):
    return _get(job_id)


@router.get("/{job_id}/events")
async def get_job_events(job_id: str):
    _get(job_id)
    return {"events": jobs.events(job_id)}


@router.post("/{job_id}/retry", status_code=202)
async def retry_job(job_id: str):
    _get(job_id)
    try:
        return jobs.retry(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/cancel", status_code=202)
async def cancel_job(job_id: str):
    _get(job_id)
    try:
        return jobs.cancel(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
