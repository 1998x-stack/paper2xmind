"""Single-worker processing that reuses the public paper2xmind core package."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
from dataclasses import replace
from pathlib import Path

from paper2xmind.analyzer import PaperAnalysisError
from paper2xmind.cli import ArxivToXmind
from paper2xmind.config import settings as core_settings
from paper2xmind.extractor import PDFExtractor

from app.services.jobs import JobCancelled, JobRepository
from app.services.storage import StorageService
from app.services.xmind_parser import XMindParser

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]


class PaperWorker:
    def __init__(self, repository: JobRepository, storage: StorageService):
        self.repository = repository
        self.storage = storage

    async def process(self, job: dict) -> None:
        job_id, paper_id = job["id"], job["paper_id"]
        work = self.storage.data_dir / "work" / job_id
        work.mkdir(parents=True, exist_ok=True)
        try:
            config = replace(
                core_settings, data_dir=str(work),
                output_dir=str(work),
                xmind_base_path=str(REPO_ROOT / "xmind_base"),
            )
            # Stages and state updates share the same persisted DB.
            def check(stage: str) -> None:
                self.repository.stage(job_id, stage)

            converter = ArxivToXmind(settings=config)
            generated = await converter.convert(job["source"], stage_callback=check)
            check("VERIFYING")
            generated_path = Path(generated)
            tree = XMindParser.convert_to_tree(XMindParser.parse_xmind_file(generated_path))
            if tree is None or not tree.get("children"):
                raise ValueError("XMIND_ROUNDTRIP_FAILED: Invalid generated XMind tree")

            # Find the local PDF, including downloaded arXiv input.
            source = Path(job["source"])
            if not source.is_file():
                candidates = list(work.glob("*.pdf"))
                if not candidates:
                    raise FileNotFoundError("Downloaded paper not found")
                source = candidates[0]
            full_text, _pages = PDFExtractor(config).extract_text_from_pdf(str(source), save_txt=False)
            if not full_text.strip():
                raise ValueError("PARSER_EMPTY: No extractable PDF text")

            paper_dir = self.storage.papers_dir / paper_id
            paper_dir.mkdir(parents=True, exist_ok=True)
            # Atomic artifact publication (never expose a partial ZIP).
            tmp = paper_dir / f"mindmap.{job_id}.tmp"
            shutil.copyfile(generated_path, tmp)
            os.replace(tmp, paper_dir / "mindmap.xmind")
            pdf_tmp = paper_dir / f"source.{job_id}.tmp"
            shutil.copyfile(source, pdf_tmp)
            os.replace(pdf_tmp, paper_dir / "source.pdf")
            await self.storage.save_paper_content(
                paper_id, tree["title"], full_text,
                metadata={"pages": len(_pages), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
            )
            self.repository.finish(job_id, state="READY")
        except JobCancelled:
            self.repository.finish(job_id, state="CANCELLED")
        except PaperAnalysisError as exc:
            self.repository.finish(
                job_id, state="FAILED_RETRYABLE" if exc.code == "LLM_IO_ERROR" else "FAILED_TERMINAL",
                error_code=exc.code, error_message=str(exc),
            )
        except (OSError, TimeoutError) as exc:
            logger.exception("Transient processing failure for %s", job_id)
            self.repository.finish(job_id, state="FAILED_RETRYABLE",
                                   error_code="IO_ERROR", error_message=type(exc).__name__)
        except Exception as exc:
            logger.exception("Processing failed for %s", job_id)
            code = str(exc).split(":")[0]
            self.repository.finish(job_id, state="FAILED_TERMINAL",
                                   error_code=code if code.isupper() and len(code) < 64 else "PIPELINE_FAILED",
                                   error_message=type(exc).__name__)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    async def run(self, interval: float = 0.4) -> None:
        """Intentionally one active paper per process; SQLite protects claiming."""
        self.repository.recover()
        while True:
            job = self.repository.claim()
            if job:
                await self.process(job)
            else:
                await asyncio.sleep(interval)
