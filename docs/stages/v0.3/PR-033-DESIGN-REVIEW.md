# V0.3 PR-033 — Structure-aware Semantic Chunker

> **Design review and implementation record**
>
> Baseline: feat/v0.3-pr032-parser-router. This PR adds an independent
> DocumentIR -> ChunkManifest path only; it does not replace the V0.2
> API/Worker or send text to an LLM.

## 1. Review findings and engineering decisions

### P0-1: Plain-text chunking destroys source lineage

Fixed: ChunkFragment refers directly to DocumentBlock by block_id, page_index,
section_id and Unicode *code-point* offsets [start_cp,end_cp) in
DocumentBlock.normalized_text (NFC+LF). A SHA-256 fingerprint of that precise
text is stored. The independent validator checks the copied quote, offsets,
hash, page and section against the original DocumentIR. A block's BBox is only
coarse PDF localization; neither a block nor a fragment proves individual
glyph coordinates or scientific validity.

### P0-2: Text overlap may create duplicate "facts"

Fixed: every ChunkFragment has a role: primary or context. Across the entire
chunk manifest, every normalized source code point must appear in primary
exactly once, in source order. Context must appear before primaries within
its chunk and refer only to source offsets covered by earlier primaries.
The validator rejects overlap improperly marked primary, missing primary
coverage, duplicated primary offsets and cross-revision references.

### P0-3: Naive separators break exact citations

If a paragraph is split at offset k, emitting "left\\n\\nright" silently
changes the normalized source quote crossing k. Fixed via
render_fragments(): fragments from the **same source block** whose offsets
are adjacent are joined with no artificial characters. Different blocks use
a double newline. Context suffix and next primary are also joined without
a separator when their source offsets meet. A separately annotated gold
quote crossing the boundary now survives inside the next chunk.

### P0-4: Large tables/formulas cannot be arbitrarily split

The following kinds are atomic: table, equation, figure, caption, heading.
If an atomic block exceeds the max budget, emit ATOMIC_BLOCK_TOO_LARGE,
not a silently truncated or misattributed block. Oversized prose may be
split at safe code-point boundaries with preference for sentence or
whitespace positions, preserving every character. Emoji sequences,
combining marks and ZWJ boundary risks have explicit safeguards.

### P1-5: "Token budget" requires a tokenizer identity

UTF8ByteCounter is the default; it counts UTF-8 bytes, not model tokens.
For standard byte-level BPE its byte count is a conservative upper bound,
but it is NOT an exact usage count and may not apply to other tokenizers.
TiktokenCounter can be explicitly installed and selected by encoding;
its reported model_tokens are exact only for that encoding, not for an
unrelated local Qwen model. The manifest records tokenizer_id, budget_unit,
max_budget_units, source parser config hash and a deterministic chunker config
hash. Both content and separators are counted by the selected counter.

No claim is made about chat-template/tool-call overhead or model context
window. Downstream callers should reserve model-specific tokens separately.

### P1-6: Section and page boundaries are explicit

Chunker reads DocumentIR.blocks in (page_index, reading_order) order.
Changing section_id forces a new chunk and prevents context spillover.
The page_policy configuration may allow cross-page concatenation (while
retaining exact page index per fragment), or enforce hard page breaks.
A candidate heading starts a fresh chunk when possible. If DocumentIR
has no sections (PR-031 native parser), the system cannot invent them;
PR-032's Docling adapter may provide unverified structural section IDs.

### P1-7: Independent verification is mandatory

validate_chunk_manifest reconstructs source coverage from the original
DocumentIR, not from ChunkManifest copied strings. In addition it checks:
- source PDF/revision/parser-config identity;
- counter identity and exact emitted content budget, including separators;
- primary section and chronological source order;
- SHA, code-point spans, page and block ownership;
- context offsets only from preceding primary coverage;
- no missing/duplicated primary code points.

The chunker calls validation before publishing a manifest. Other consumers
must independently call it after reading JSON from disk or API.

## 2. Dataflow

    DocumentIR (PR-030/031/032)
       -> ordered DocumentBlock normalized spans
       -> atomic-content protection and prose slicing
       -> greedy primary planning by section/page and exact counter
       -> optional bounded context suffix from previous primaries
       -> render_fragments (no artificial split-in-block separators)
       -> ChunkManifest + source/config/tokenizer provenance
       -> Independent validation and golden span evaluation
       -> [future PR-034] evidence-grounded claim extraction

No LLM prompt construction, RAG vector index, API mutation or XMind export
was changed by PR-033.

## 3. Data contract

ChunkManifest schema: document_chunks/1.0.0

- revision_id, pdf_sha256, parser_config_sha256, config_sha256
- tokenizer_id, budget_unit (utf8_bytes or model_tokens)
- max_budget_units, overlap_budget_units
- chunks[]: chunk_id, sequence, section_id, content,
  budget_units, primary_units, context_units, fragments[]
- fragments[]: block_id, page_index, section_id,
  start_cp/end_cp, quote text, text_sha256, role

Immutable Pydantic models, strict extra=forbid, plus independent
cross-document validation.

## 4. Offline usage

Default byte-budget mode (no extra tokenizer package):

    pip install -e ".[dev]"
    python -m paper2xmind.chunking output/paper.document-ir.json \
      --output output/paper.chunks.json \
      --budget 4096 --overlap 256 --page-policy allow

Strict page boundaries:

    python -m paper2xmind.chunking output/paper.document-ir.json \
      --output output/paper.chunks.json \
      --budget 4096 --overlap 128 --page-policy hard

Optional exact tiktoken encoding (not automatically the right Qwen budget):

    pip install -e ".[tokenizers,dev]"
    python -m paper2xmind.chunking output/paper.document-ir.json \
      --output output/paper.chunks.json \
      --tiktoken-encoding cl100k_base \
      --budget 2048 --overlap 128

The CLI accepts direct DocumentIR JSON and both PR-031 ParseResult or PR-032
RoutedDocument wrapped JSON (key "document"). It atomically publishes
canonical JSON only if validation succeeds.

## 5. Evaluation: evidence recall and redundancy

Evaluator: evals/benchmarks/chunker_groundtruth_v033.py

A human-reviewed local manifest must include:
- corpus_name and cases[] entries;
- each case's relative DocumentIR path, its SHA-256 and a nonempty license_note;
- annotated gold_spans (block_id, start_cp, end_cp, exact quote).

Two separate quote-recall outcomes:
1. primary_fragment_recall: gold ranges fully present in a contiguous span
   formed only from primary fragments in one emitted chunk;
2. including_overlap_recall: gold ranges fully present in a contiguous span
   formed from primary+context in the same chunk.

The evaluator **does not** reconstruct an original PDF or validate that an
LLM's answer semantically follows from the retrieved quotes. Evidence is
defined as exact source-span containment only.

Coverage:
- primary_coverage = primary code points / all source code points.
  The independent validator requires exactly 100% with zero duplicate
  primaries or the run is FAILED; it never reports a partially valid "success".

Redundancy:
- context_redundancy_ratio = context codepoints /
  (primary codepoints + context codepoints).
  This measures intentional source-text duplication, *not* duplicated
  scientific claims or model cost in tokens.

Synthetic CI fixtures demonstrate mechanics only. The repository currently
does not contain an independently annotated rights-cleared real research
corpus, so real-document evidence recall and time/accuracy trade-offs
remain UNMEASURED.

## 6. CI / acceptance matrix

- Three Python versions (3.10/3.11/3.12), full core tests, backend regressions,
  frontend TypeScript/Vite build.
- Exact source reconstruction with multiple blocks, section changes,
  cross-page policy, long paragraphs and sentence-aware boundaries.
- Atomic table/equation/figure/caption/heading over-budget errors.
- Chinese NFC normalization, emoji and code-point offsets.
- Bounded overlap marked context; no duplicated primary or fake context.
- Same-block adjacent fragment continuity and cross-boundary gold retrieval.
- Tampered SHA/quote, missing fragment, wrong counter or PDF hash rejected.
- Deterministic IDs, config fingerprints and canonical JSON output.
- CLI atomic output and independent manifest source/permission-note checks.
- Empty/scanned DocumentIR never fabricates nonempty chunks.

## 7. Known limitations and follow-on work

- Atomically oversized tables fail explicitly: PR-034 must decide whether to
  create separately addressable table-cell evidence with a new schema.
- Complex Unicode grapheme handling is conservative but not a full UAX #29
  grapheme segmenter. Exact offsets are validated and no characters dropped.
- Punctuation-aware splitting is heuristic, not sentence parsing.
- PR-032 Docling extraction has not yet been measured on an annotated real
  scientific corpus. Chunker validation does not cure an incorrect parser.
- Cross-block evidence is not claimed to be a single source span.
- Model-specific tokenizer integration for Qwen (for example a supported HF
  tokenizer wrapper) and prompt-context reserves belong to PR-034.
- Stable IR references are not equivalent to actual source verification
  against PDF screenshots; scientific support is PR-035.
- Existing V0.2 Worker/API stays unchanged until PR-036 feature-gated rollout.

## 8. Next stage

PR-034: separate ClaimCandidate extraction by chunk from independent
Claim/Evidence verification, ensure all candidate citations refer to
ChunkFragment primary/context source spans, and deduplicate overlap-induced
candidate claims by evidence and normalized proposition, not by title alone.
