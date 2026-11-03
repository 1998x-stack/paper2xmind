# V0.3 PR-032 — DocumentProfiler & ParserRouter
## 代码审查、架构设计与验收记录

> 本 PR 堆叠于 PR-031 的 feature branch，不直接向 main 合并；
> PR-031 的 PyMuPDF Block Parser 不被修改，V0.2 上传/任务/导图仍保持不变。
> 当前版本首次提供结构化解析的显式选择与结果质量门禁。
> **这是解析工程基础设施，不是科学结论验证器。**

## 1. Deep Review：PR-031 暴露的根因

1. **Diagnostics 不是决策引擎。** PR-031 提供各页 warnings，
   但调用方不知道何时应当做结构化升级，何时只保留廉价 PyMuPDF。
   若直接对所有 PDF 调用 Docling，CPU/RAM 和模型启动开销大幅增加，
   也不会确保每个文档都得到更好结果。
2. **输出更多文本并不代表解析更准确。** Docling 可能将表格转换成 Markdown、
   合并重复页眉或省略边注。只通过 JSON Schema 是不够的。
   本 PR 首先要求 hash、revision、页数、display bbox 和逐页最低文字保留率；
   这些是确定性安全检查，不是语义准确率证明。
3. **Docling 的 provenance 是不同坐标契约。** page_no 从 1 开始，
   bbox 的 coord_origin 可为 TOPLEFT 或 BOTTOMLEFT。PR-030 的
   DocumentIR 使用 page_index 从 0 开始且 bbox 为显示页 top_left_pt。
   对旋转/CropBox 页面若不能证明两个系统的尺寸一致，则拒绝升级，
   禁止硬猜坐标变换。
4. **跨页 item 不能重复归属整个原文。** Docling item.prov 可能包含多个
   provenance。PR-032 不把同一个段落文本重复贴到不同页面以制造引用；
   多 provenance item 保守跳过并记录警告，待 PR-033/034 做 charspan
   对齐之后再升级策略。
5. **Docling 的模型权重与实际服务风险。** 依赖库带来模型资源、
   缓存和首次初始化成本。默认不安装、不运行、不进入 API/Worker。
   Docling 依赖与包版本进入配置指纹，但模型工件权重 hash 尚未纳入，
   所以目前不能宣称跨设备完全可复现。

## 2. 设计边界和组件

Data flow:

    PDF
      ↓
    StructuredPDFBlockParser (PR-031)
      ├─ ParseResult(DocumentIR, PageDiagnostics)
      ↓
    DocumentProfiler
      ├─ IMAGE_ONLY_PAGES / SPARSE_TEXT_PAGES
      ├─ HEURISTIC_TWO_COLUMN / AMBIGUOUS_COLUMNS
      ├─ POSSIBLE_TABLE_TEXT / NONHORIZONTAL_TEXT
      ├─ SOURCE_BLOCKS_SKIPPED / NO_EXTRACTABLE_TEXT
      ↓
    ParserRouter
      ├─ native (default, always cheap, no Docling import)
      ├─ auto (only when enabled and risk signal exists)
      └─ structured (explicit --enable-docling)
           ↓
        DoclingDocumentAdapter
           ↓
        DocumentIR v1
           ↓
        Gate: source hash, revision, page geometry, source page coverage
           ├─ accept: selected_parser=docling
           ├─ reject: native fallback with explicit reason
           └─ strict reject: RouteError (when fallback disabled)
      ↓
    RoutedDocument(DocumentIR, profile, attempts, diagnostics)

### 2.1 Profile Signals

Signals are discrete heuristics, never decimal confidence or ungrounded
accuracy rates. Scanned/image-only pages remain image-only in the
PyMuPDF baseline. Table-caption detection supplements PR-031 layout warnings.
Two-column heuristics are treated as "higher risk", not "incorrect".

ProfileConfig:
- sparse_chars_per_page=60, minimum_sparse_pages=2
- minimum_two_column_pages=1

The thresholds are engineering defaults, and must be tuned using the
independent rights-cleared corpus before production automatic escalation.

### 2.2 Routing policies

| mode | enable_docling | trigger | behavior |
|---|---|---|---|
| native | False (default) | always | native DocumentIR; no heavy dependency |
| auto | False | risk/no risk | stay native, risk surfaced |
| auto | True | no risk | stay native |
| auto | True | any risk | try Docling, validate result, else fallback/error |
| structured | True | forced | try Docling regardless of risks |
| structured | False | invalid | configuration validation fails |

The default failure policy is explicit fallback to unchanged native DocumentIR
with ParserAttempt(reason=<machine-readable-error>).
In strict mode (fallback_on_error=False), throw RouteError and publish no
structured output. No code should interpret a failed upgrade as VALIDATED.

### 2.3 Acceptance gate

- Docling output must be a valid DocumentIR, including all cross-references.
- source_sha256, pdf_sha256, revision_id identical to the PyMuPDF baseline.
- Same count of PDF pages, same page_index/rotation/display page dimensions.
- Every page with native text must retain at least a configurable 80% character
  count. A long table on one page cannot conceal a zero-text second page.
- At least one character of Docling text overall.
- Docling's structured metadata/table Markdown is *not* evidence of
  verified source quotation or numeric/table-cell semantics.

This retention gate is only a crude regression filter: a longer paraphrase
could still be incorrect. PR-035 will independently verify exact quotations,
value attribution and model judgement.

### 2.4 Adapter details

- Docling v2 API: DocumentConverter.convert; DoclingDocument.iterate_items;
  DocItem.prov[0].page_no and BoundingBox.coord_origin.
- A table is kept as a table-kind block, with reconstructed Markdown text.
  Table-cell geometry, row/column spans and formula structure are NOT
  represented in DocumentIR v1; PR-033+ should extend the schema only after
  a backwards-compatibility RFC.
- If source coord_origin BOTTOMLEFT, convert y coordinates by page height.
- If TOPLEFT, use source page units after verifying width/height against
  PyMuPDF display dimensions. Rotated/cropped mismatch => reject.
- DocumentIR.sections is based on section_header labels; depth is an
  inference from Docling hierarchy, not a verified scientific outline.
- Multi-provenance item is skipped rather than duplicating entire text.
  Skips can fail per-page coverage gate and then trigger native fallback.

## 3. Reproducible interface and operations

Default lightweight installation (no Docling models):

    pip install -e ".[dev]"
    python -m paper2xmind.parsers.router_cli ./paper.pdf \
      --revision-id 0123456789abcdef0123456789abcdef \
      --output ./output/native.json

Explicit heavy installation/selection:

    pip install -e ".[docling,dev]"
    python -m paper2xmind.parsers.router_cli ./paper.pdf \
      --revision-id 0123456789abcdef0123456789abcdef \
      --output ./output/structured.json \
      --mode structured --enable-docling --no-fallback

Auto-upgrade with explainable fallback:

    python -m paper2xmind.parsers.router_cli ./paper.pdf \
      --output ./output/routed.json --mode auto --enable-docling

Warning: Docling may download/use local layout/table model artifacts and
its first conversion can be resource intensive. Model cache, downloads,
timeouts, isolation, model-artifact hashes, cancellation, and service-facing
authorization must be explicitly controlled before this is deployed in a
network-facing Worker (planned PR-036). PR-032 does not expose a service API.

## 4. Real annotated paper evaluation contract

Evaluator: evals/benchmarks/parser_groundtruth_v032.py

A manifest must be supplied with independently human-reviewed annotations:
- corpus_name; each paper has relative path, sha256 and license_note
- pages contain zero-based page_index plus ordered_snippets in true reading order
- comparator finds unique exact normalized source strings on each page
- snippet_coverage = uniquely found snippets / all annotated snippets
- order_pair_accuracy = correctly ordered pairs / all annotated ordered pairs,
  counting missing/ambiguous snippets as incorrect pairs
- returns parse failures explicitly: NEVER silently aggregate an error as
  an accurate or improved result

Minimal manifest (replace the hash with the actual file SHA-256):

    {
      "schema_version": "paper2xmind_pdf_gt_v1",
      "corpus_name": "rights-cleared-annotated-papers",
      "papers": [
        {
          "id": "paper1",
          "path": "papers/paper1.pdf",
          "sha256": "<64 lowercase hex characters>",
          "license_note": "license/permission and provenance",
          "pages": [{
            "page_index": 0,
            "ordered_snippets": [
              "first human-checked passage",
              "second human-checked passage"
            ]
          }]
        }
      ]
    }

    python evals/benchmarks/parser_groundtruth_v032.py ./manifest.json \
      --output ./results/native.json
    python evals/benchmarks/parser_groundtruth_v032.py ./manifest.json \
      --include-docling --output ./results/compare.json

A license_note is supplied by the corpus curator and is not independently
proof of legal permission. PR-032 **does not include a real annotated corpus**,
so real-paper accuracy is UNMEASURED. All default CI evaluations are
synthetic regression tests. No external document content is downloaded.

## 5. CI / acceptance

- Default Python 3.10 / 3.11 / 3.12; Core, Backend, frontend regressions.
- Mock Docling-v2 converter validates TOPLEFT/BOTTOMLEFT mapping and one-based
  page number conversion without requiring heavyweight model downloads.
- Profile tests include simple PDF, two columns, image-only pages and
  table captions; auto mode does not invoke unneeded Docling adapters.
- Error cases include partial-success status, wrong document hash,
  wrong page dimensions/rotation, missing page text, missing provenance,
  ambiguous cross-page provenance, malformed bounding boxes.
- Strict mode returns an error rather than silently publishing native output.
- Independent evaluator's synthetic data checks exact quote coverage, reverse
  order yielding 0% pair accuracy, missing snippets, path traversal and hash.
- CLI writes JSON atomically, no partial artifacts after failure.

## 6. Incomplete (explicit)

- Actual Docling runtime/model-weight E2E in the default CI: NOT RUN.
- Real licensed annotated paper benchmark: NOT AVAILABLE.
- OCR quality / complex table-cell layout / formula fidelity: NOT MEASURED.
- Production Worker integration, resource isolation and cancellation: NOT ENABLED.
- Glyph-level evidence anchoring and scientific support: PR-034/035.
- Multi-page item span alignment, semantic section-aware chunking: PR-033.

## 7. Follow-on development

PR-033 — semantic DocumentIR Chunker:
1. Carry block_id/page_index/section_id and exact normalized quote offsets;
2. Avoid splitting tables and numbered results across chunks;
3. Use tokenizer-aware budget and controllable overlap;
4. Measure chunk evidence recall, duplicate overlap and source completeness
   with both baseline and Docling IR on annotated PDFs.

PR-034/035 — source-grounded claims and independent verification.
PR-036 — revisions/artifacts + authenticated API + isolated worker rollout.

## 8. External reference contracts

Docling v2 iterate_items/table/provenance:
https://docling.org/doc/
https://docling-project.github.io/docling/reference/docling_document/
https://github.com/docling-project/docling/blob/main/docling/.agents/skills/docling/references/python-sdk.md

PyMuPDF coordinates and text extraction:
https://pymupdf.readthedocs.io/en/latest/page.html
https://pymupdf.readthedocs.io/en/latest/app1.html
