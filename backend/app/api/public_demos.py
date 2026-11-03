"""Read-only public demo allowlist. It cannot read private papers or SQLite."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.security.private_api import public_demo_enabled
from app.services.demo_catalog import DEMO_ID, TITLE, demo_snapshot

router = APIRouter(prefix="/api/public/demos", tags=["public-demo"])


def _enabled():
    if not public_demo_enabled():
        raise HTTPException(status_code=404, detail="Demo not enabled")


@router.get("")
def list_public_demos():
    _enabled()
    return {"demos": [{
        "demo_id": DEMO_ID,
        "title": TITLE,
        "source_kind": "original_synthetic_pdf",
    }]}


@router.get("/{demo_id}")
def get_public_demo(demo_id: str):
    _enabled()
    if demo_id != DEMO_ID:
        raise HTTPException(status_code=404, detail="Unknown demo")
    return demo_snapshot()[0]


@router.get("/{demo_id}/source.pdf")
def get_public_demo_pdf(demo_id: str):
    _enabled()
    if demo_id != DEMO_ID:
        raise HTTPException(status_code=404, detail="Unknown demo")
    return Response(
        content=demo_snapshot()[1],
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="original-synthetic-example.pdf"',
                 "X-Content-Type-Options": "nosniff"},
    )
