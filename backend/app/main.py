"""FastAPI application: persistent SQLite queue and one cooperative local worker."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import categories, chat, jobs as jobs_api, papers, evidence, public_demos, research_maps
from app.services.jobs import JobRepository
from app.services.processor import PaperWorker
from app.services.storage import StorageService
from app.config import settings
from app.security.private_api import private_api_guard, deployment_mode

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = JobRepository(settings.data_dir)
    storage = StorageService(settings.data_dir)
    task = None
    if (os.getenv("P2X_DISABLE_WORKER", "0") != "1"
            and (deployment_mode() == "local"
                 or os.getenv("P2X_ALLOW_PRIVATE_WORKER") == "1")):
        task = asyncio.create_task(PaperWorker(repo, storage).run())
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Paper Research Platform", version="0.2.0", lifespan=lifespan)
app.middleware("http")(private_api_guard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(papers.router)
app.include_router(jobs_api.router)
app.include_router(chat.router)
app.include_router(categories.router)
app.include_router(evidence.router)
app.include_router(public_demos.router)
app.include_router(research_maps.router)


@app.get("/")
async def root():
    return {"message": "Paper Research Platform API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
