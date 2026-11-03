"""Pluggable budget counters.

Default UTF-8 byte count is a conservative byte-level BPE *upper bound*;
it is NOT an exact token count for arbitrary LLMs. Exact per-model token
budgets require a matching model tokenizer (TiktokenCounter is optional).
Never label a byte budget as measured model-token usage.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class BudgetCounter(Protocol):
    @property
    def tokenizer_id(self) -> str: ...
    @property
    def budget_unit(self) -> Literal["utf8_bytes", "model_tokens"]: ...
    def count(self, text: str) -> int: ...


class Utf8ByteCounter:
    @property
    def tokenizer_id(self) -> str:
        return "utf8_bytes/v1"

    @property
    def budget_unit(self) -> Literal["utf8_bytes"]:
        return "utf8_bytes"

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))


class TiktokenCounter:
    """Exact count for the chosen tiktoken encoding only; lazy import."""
    def __init__(self, encoding_name: str = "cl100k_base"):
        try:
            import tiktoken
        except ImportError as exc:
            raise RuntimeError("Install paper2xmind[tokenizers] for tiktoken") from exc
        self._encoding = tiktoken.get_encoding(encoding_name)
        self._name = encoding_name

    @property
    def tokenizer_id(self) -> str:
        return "tiktoken/" + self._name

    @property
    def budget_unit(self) -> Literal["model_tokens"]:
        return "model_tokens"

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))
