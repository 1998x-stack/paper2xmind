"""First-stage durable job state contracts (no external model calls)."""
import pytest

from app.services.jobs import JobCancelled, JobRepository


def test_job_create_dedup_and_events(tmp_path):
    repo = JobRepository(tmp_path)
    a = repo.create(source="source.pdf",source_key="sha1",source_name="file.pdf")
    b = repo.create(source="source.pdf",source_key="sha1",source_name="file.pdf")
    assert a["id"] == b["id"]
    assert repo.claim()["id"] == a["id"]
    repo.stage(a["id"], "EXTRACTING")
    repo.finish(a["id"], state="READY")
    assert repo.get(a["id"])["state"] == "READY"
    assert len(repo.events(a["id"])) >= 3


def test_cancel_before_claim(tmp_path):
    repo = JobRepository(tmp_path)
    a = repo.create(source="a",source_key="a",source_name="a")
    assert repo.cancel(a["id"])["state"] == "CANCELLED"
    assert repo.claim() is None


def test_cooperative_cancel_running(tmp_path):
    repo = JobRepository(tmp_path)
    a = repo.create(source="a",source_key="a",source_name="a")
    repo.claim()
    assert repo.cancel(a["id"])["state"] == "CANCEL_REQUESTED"
    with pytest.raises(JobCancelled):
        repo.stage(a["id"], "EXPORTING")
    repo.finish(a["id"], state="CANCELLED")
    assert repo.get(a["id"])["state"] == "CANCELLED"


def test_expired_lease_recovery(tmp_path):
    repo = JobRepository(tmp_path)
    job = repo.create(source="x",source_key="k",source_name="x")
    repo.claim(lease_seconds=0)
    repo.recover()
    assert repo.get(job["id"])["state"] == "QUEUED"
