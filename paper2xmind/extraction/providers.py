"""Explicit online adapter and deterministic fixture provider.

No network, API key or automatic model calls in import paths. Online
generation needs an explicit caller-created OpenAIClaimModel or CLI flag.
"""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import ClaimExtractionError, ModelRequest


class FixtureClaimModel:
    """Responses keyed by exact chunk IDs, for offline fixtures and evaluation."""
    def __init__(self, responses: dict[str, str], *, model_id: str = "fixture-model/v1"):
        self._responses = dict(responses)
        self._id = model_id

    @property
    def model_id(self) -> str:
        return self._id

    def generate(self, request: ModelRequest) -> str:
        try:
            return self._responses[request.chunk_id]
        except KeyError as exc:
            raise ClaimExtractionError("FIXTURE_CHUNK_NOT_FOUND",
                                       "No fixture for the requested chunk") from exc


class OpenAIClaimModel:
    """Opt-in compatibility adapter; caller controls endpoint and credentials.

    JSON mode constrains output format, not citation accuracy. Pydantic and
    exact DocumentIR source checks remain mandatory after model output.
    """
    def __init__(self, model_id: str, *, api_key: str | None = None,
                 base_url: str | None = None, timeout: float = 60.0,
                 max_output_tokens: int = 2048):
        if not model_id.strip():
            raise ValueError("model_id must not be empty")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ClaimExtractionError("MODEL_SDK_UNAVAILABLE", "openai SDK not installed") from exc
        kwargs = {"timeout": timeout, "max_retries": 0}
        if api_key is not None:
            kwargs["api_key"] = api_key
        if base_url is not None:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._id = model_id
        self._limit = max_output_tokens

    @property
    def model_id(self) -> str:
        return self._id

    def generate(self, request: ModelRequest) -> str:
        if request.model_id != self._id:
            raise ClaimExtractionError("MODEL_ID_MISMATCH", "Request model identity differs")
        try:
            result = self._client.chat.completions.create(
                model=self._id,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=self._limit,
            )
        except Exception as exc:
            raise ClaimExtractionError("MODEL_PROVIDER_FAILURE",
                                       "Online provider call failed") from exc
        text = result.choices[0].message.content if result.choices else None
        if not isinstance(text, str):
            raise ClaimExtractionError("MODEL_RESPONSE_EMPTY", "Model returned no text")
        return text
