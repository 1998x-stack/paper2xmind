"""PH-00: isolate anonymous public demos from all legacy private APIs.

The old V0.2 routes are single-workspace, NOT tenant-aware. In public
deployment only an operator with an explicit admin credential can access
ANY non-demo legacy /api endpoint. Never infer public access from CORS or
React route visibility.

Protected public mode is the DEFAULT. Anonymous legacy local mode requires
explicit opt-in and must only be used on a localhost development instance.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

ALLOWED_MODES = frozenset({"local", "public"})


def deployment_mode() -> str:
    return os.environ.get("P2X_DEPLOYMENT_MODE", "public")


def public_demo_enabled() -> bool:
    return deployment_mode() == "public" and os.environ.get("P2X_PUBLIC_DEMO_ENABLED") == "1"


def _admin_token_valid(raw_authorization: str | None) -> bool:
    if not raw_authorization or not raw_authorization.startswith("Bearer "):
        return False
    raw = raw_authorization[7:]
    if not 24 <= len(raw) <= 512:
        return False
    try:
        data = json.loads(os.environ.get("P2X_EVIDENCE_AUTH_JSON", "{}"))
    except (TypeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    matched = False
    # Deliberately examine every actor, including users without admin roles.
    for item in data.values():
        if not isinstance(item, dict) or "admin" not in item.get("roles", []):
            continue
        digest = item.get("token_sha256")
        if isinstance(digest, str) and len(digest) == 64:
            matched = hmac.compare_digest(actual, digest) or matched
    return matched


async def private_api_guard(request: Request, call_next) -> Response:
    """Fail-closed guard for an entire /api namespace in public mode."""
    mode = deployment_mode()
    path = request.scope.get("path", "")
    if mode not in ALLOWED_MODES:
        return JSONResponse({"detail": "DEPLOYMENT_MODE_INVALID"}, status_code=503)
    if mode != "public" or not (path == "/api" or path.startswith("/api/")):
        return await call_next(request)

    # Strict public namespace; no "/api/public/demosXYZ" lookalikes.
    if path == "/api/public/demos" or path.startswith("/api/public/demos/"):
        if not public_demo_enabled():
            return JSONResponse({"detail": "Public demo disabled"}, status_code=404)
        response = await call_next(request)
        response.headers["Cache-Control"] = "public, max-age=60"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # PR-035 evidence routes have their own role-based bearer checks,
    # including reviewer HMAC verification. Do NOT bypass those checks.
    if path == "/api/evidence" or path.startswith("/api/evidence/"):
        response = await call_next(request)
    elif _admin_token_valid(request.headers.get("Authorization")):
        response = await call_next(request)
    else:
        return JSONResponse(
            {"detail": "Private workspace requires admin authorization"},
            status_code=401,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
