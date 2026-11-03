"""PR-033 source-grounded, budget-bound semantic chunking."""
from .contracts import (
    CHUNK_SCHEMA_VERSION, ChunkingError, ChunkerConfig, ChunkFragment,
    DocumentChunk, ChunkManifest,
)
from .budget import BudgetCounter, Utf8ByteCounter, TiktokenCounter
from .chunker import StructureAwareChunker
from .validation import (
    ChunkAudit, GoldSpan, GoldSpanReport, validate_chunk_manifest, evaluate_gold_spans,
)

__all__ = [
    "CHUNK_SCHEMA_VERSION", "ChunkingError", "ChunkerConfig", "ChunkFragment",
    "DocumentChunk", "ChunkManifest", "BudgetCounter", "Utf8ByteCounter",
    "TiktokenCounter", "StructureAwareChunker", "ChunkAudit", "GoldSpan", "GoldSpanReport",
    "validate_chunk_manifest",
    "evaluate_gold_spans",
]
