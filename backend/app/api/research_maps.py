"""V0.4 PH-02 private ResearchMap read projection.

In P2X_DEPLOYMENT_MODE=public, the global private API guard requires an
ADMIN credential before invoking this route. V0.3 evidence signatures are
also independently checked before any reviewed state appears in a map.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Response

from app.config import settings
from app.api.evidence import _authority, _verified_read
from app.services.evidence_repo import EvidenceRepository, EvidenceStoreError
from paper2xmind.domain import DocumentIR
from paper2xmind.chunking import ChunkManifest
from paper2xmind.extraction import ClaimExtractionLedger
from paper2xmind.review import ReviewAnalysis, ReviewOutcome, ReviewError
from paper2xmind.research_map import ResearchMap, project_research_map

router = APIRouter(prefix="/api/research/papers", tags=["research-map"])


@router.get("/{paper_id}/maps/latest", response_model=ResearchMap)
def latest_map(paper_id: str, response: Response):
    if (os.environ.get("P2X_EVIDENCE_ENABLED", "0") != "1"
            or os.environ.get("P2X_RESEARCH_MAP_ENABLED", "0") != "1"):
        raise HTTPException(status_code=404, detail="Research map unavailable")
    try:
        stored = EvidenceRepository(settings.data_dir).latest(paper_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="No published evidence")
        # V0.3's trusted read revalidates signed reviewer status.
        stored = _verified_read(stored)
        documents = stored["documents"]
        if "claims" not in documents:
            raise HTTPException(
                status_code=409,
                detail="Source is published but candidate extraction is not yet available",
            )
        document = DocumentIR.model_validate(documents["document_ir"])
        chunks = ChunkManifest.model_validate(documents["chunks"])
        ledger = ClaimExtractionLedger.model_validate(documents["claims"])
        analysis = (ReviewAnalysis.model_validate(documents["review_analysis"])
                    if "review_analysis" in documents else None)
        outcome = (ReviewOutcome.model_validate(stored["review_outcome"])
                   if stored.get("review_outcome") is not None else None)
        research_map = project_research_map(
            document, chunks, ledger, analysis=analysis,
            outcome=outcome,
            authority=_authority() if outcome is not None else None,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return research_map
    except HTTPException:
        raise
    except (EvidenceStoreError, ReviewError, ValueError) as exc:
        # Never leak document contents or reviewer secrets in errors.
        raise HTTPException(
            status_code=422, detail=getattr(exc, "code", "RESEARCH_MAP_INVALID"),
        ) from exc
