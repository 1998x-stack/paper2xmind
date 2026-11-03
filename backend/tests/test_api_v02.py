"""HTTP contracts: upload → queued job → cancel; no real API keys required."""
import io
from fastapi.testclient import TestClient

from app.main import app
from app.api import papers as papers_api
from app.api import jobs as jobs_api
from app.services.jobs import JobRepository


def test_upload_and_job_lifecycle(tmp_path, monkeypatch):
    repo = JobRepository(tmp_path)
    from app.services.storage import StorageService
    storage = StorageService(tmp_path)
    monkeypatch.setattr(papers_api, "jobs", repo)
    monkeypatch.setattr(papers_api, "storage", storage)
    monkeypatch.setattr(jobs_api, "jobs", repo)
    with TestClient(app) as client:
        response = client.post("/api/papers/upload",
            files={"file": ("science.pdf", b"%PDF-1.4\nfixture", "application/pdf")})
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        job = client.get(data["links"]["job"])
        assert job.status_code == 200
        assert job.json()["state"] == "QUEUED"
        cancel = client.post(data["links"]["job"] + "/cancel")
        assert cancel.status_code == 202
        assert cancel.json()["state"] == "CANCELLED"


def test_non_pdf_rejected(tmp_path, monkeypatch):
    from app.services.storage import StorageService
    monkeypatch.setattr(papers_api, "jobs", JobRepository(tmp_path))
    monkeypatch.setattr(papers_api, "storage", StorageService(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/papers/upload",
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")})
    assert response.status_code == 400
