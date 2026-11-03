"""PR-030 strict domain contracts, evidence correctness and legacy safety."""
import hashlib
import json

import pytest
from pydantic import ValidationError

from paper2xmind.domain import (
    Claim, ClaimCandidate, promote_claim_candidate, DocumentIR, DomainValidationError, EvidenceCandidate, EvidenceRef,
    MindNode, SupportAssessment, adapt_legacy_tree, canonical_serialize,
    canonical_sha256, normalize_text_v1, resolve_evidence_candidate,
    validate_document_references, validate_evidence_spans,
    validate_knowledge_references,
)
from paper2xmind.domain.export_schema import SCHEMAS, export_schemas

REV = "a" * 32
PDF_SHA = "b" * 64
RAW = "F1 rises from 0.81 to 0.84.\r\nRe\u0301sume\u0301 中文 😀."


def make_doc(**changes):
    data = {
        "schema_version": "document_ir/1.0.0", "revision_id": REV,
        "pdf_sha256": PDF_SHA,
        "pages": [{"page_index": 0, "page_label": "i", "width_pt": 300,
                   "height_pt": 400, "rotation": 90, "coord_system": "top_left_pt"}],
        "blocks": [{
            "block_id": "blk_1", "page_index": 0, "kind": "paragraph",
            "reading_order": 0, "text": RAW, "normalized_text": normalize_text_v1(RAW),
            "normalization_version": "nfc_lf_v1", "bbox": [10, 20, 110, 50],
            "section_id": "sec_1",
            "extraction": {"parser_name": "pymupdf", "parser_version": "1.23",
                           "source_coord_system": "top_left_pt"},
        }],
        "sections": [{"section_id": "sec_1", "title": "Results", "level": 1,
                      "parent_section_id": None, "ordered_block_ids": ["blk_1"]}],
        "provenance": {"parser_name": "pymupdf", "parser_version": "1.23",
                       "source_sha256": PDF_SHA, "config_sha256": "c" * 64}
    }
    data.update(changes)
    return DocumentIR.model_validate(data)


def proposal(quote="F1 rises from 0.81 to 0.84", **kwargs):
    return EvidenceCandidate(revision_id=kwargs.pop("revision_id", REV),
                             block_id=kwargs.pop("block_id", "blk_1"),
                             quote=quote, **kwargs)


def test_canonical_roundtrip_and_unicode():
    doc = make_doc()
    data = canonical_serialize(doc)
    assert doc == DocumentIR.model_validate_json(data)
    assert canonical_sha256(doc) == hashlib.sha256(data).hexdigest()
    assert doc.blocks[0].normalized_text.endswith("Résumé 中文 😀.")
    assert "\r" not in doc.blocks[0].normalized_text
    assert validate_document_references(doc) == doc


@pytest.mark.parametrize("patch", [
    {"schema_version": "document_ir/9"}, {"revision_id": "invalid"},
    {"pdf_sha256": "not_sha"}, {"unknown_field": "bad"},
])
def test_invalid_schema_version_and_extra_fields(patch):
    with pytest.raises(ValidationError):
        make_doc(**patch)


def test_source_hash_and_pages():
    source = make_doc().provenance.model_dump()
    source["source_sha256"] = "d" * 64
    with pytest.raises(ValidationError, match="SOURCE_HASH_MISMATCH"):
        make_doc(provenance=source)
    page = make_doc().pages[0].model_dump()
    with pytest.raises(ValidationError, match="PAGE_INDEX_GAP_OR_DUPLICATE"):
        make_doc(pages=[page, page])


@pytest.mark.parametrize("bbox", [
    [-1, 1, 10, 20], [1, 1, 301, 20], [4, 2, 2, 20],
    [float("nan"), 2, 3, 4], [1, 2, float("inf"), 4],
])
def test_bad_bbox(bbox):
    block = make_doc().blocks[0].model_dump()
    block["bbox"] = bbox
    with pytest.raises(ValidationError):
        make_doc(blocks=[block])


def test_duplicate_block_order():
    block = make_doc().blocks[0].model_dump()
    with pytest.raises(ValidationError, match="DUPLICATE_BLOCK_ID"):
        make_doc(blocks=[block, block])
    with pytest.raises(ValidationError, match="DUPLICATE_READING_ORDER"):
        make_doc(blocks=[block, {**block, "block_id": "blk_2"}])


def test_section_membership_and_parent():
    section = make_doc().sections[0].model_dump()
    with pytest.raises(ValidationError, match="SECTION_INCOMPLETE_MEMBERSHIP"):
        make_doc(sections=[{**section, "ordered_block_ids": []}])
    with pytest.raises(ValidationError, match="SECTION_PARENT_INVALID"):
        make_doc(sections=[{**section, "parent_section_id": "unknown"}])


def test_normalization_enforced():
    block = make_doc().blocks[0].model_dump()
    block["normalized_text"] = block["text"]
    with pytest.raises(ValidationError, match="NORMALIZATION_MISMATCH"):
        make_doc(blocks=[block])


def test_exact_anchor_and_emoji_codepoint_span():
    doc = make_doc()
    ref = resolve_evidence_candidate(doc, proposal())
    assert doc.blocks[0].normalized_text[ref.start_cp:ref.end_cp] == ref.quote
    assert ref.quote_sha256 == hashlib.sha256(ref.quote.encode("utf-8")).hexdigest()
    assert validate_evidence_spans(doc, [ref])[0].localization_precision == "block"
    emoji = resolve_evidence_candidate(doc, proposal("😀"))
    assert emoji.end_cp - emoji.start_cp == 1
    validate_evidence_spans(doc, [emoji])


def test_ambiguous_quote_requires_explicit_span():
    block = make_doc().blocks[0].model_dump()
    block["text"] = "F1 F1 results"
    block["normalized_text"] = "F1 F1 results"
    doc = make_doc(blocks=[block])
    with pytest.raises(DomainValidationError, match="AMBIGUOUS_SPAN"):
        resolve_evidence_candidate(doc, proposal("F1"))
    ref = resolve_evidence_candidate(doc, proposal("F1", start_hint_cp=3, end_hint_cp=5))
    assert ref.start_cp == 3
    validate_evidence_spans(doc, [ref])


def test_wrong_revision_page_span_hash_and_duplicates():
    doc = make_doc()
    ref = resolve_evidence_candidate(doc, proposal())
    with pytest.raises(DomainValidationError, match="REVISION_MISMATCH"):
        validate_evidence_spans(doc, [ref.model_copy(update={"revision_id": "f"*32})])
    with pytest.raises(DomainValidationError, match="PAGE_MISMATCH"):
        validate_evidence_spans(doc, [ref.model_copy(update={"page_index": 2})])
    with pytest.raises(DomainValidationError, match="QUOTE_MISMATCH"):
        validate_evidence_spans(doc, [ref.model_copy(update={"start_cp": 1, "end_cp": len(ref.quote) + 1})])
    with pytest.raises(ValidationError, match="QUOTE_HASH_MISMATCH"):
        EvidenceRef.model_validate({**ref.model_dump(), "quote_sha256": "0"*64})
    with pytest.raises(DomainValidationError, match="DUPLICATE_EVIDENCE_ID"):
        validate_evidence_spans(doc, [ref, ref])
    with pytest.raises(DomainValidationError, match="REVISION_MISMATCH"):
        resolve_evidence_candidate(doc, proposal(revision_id="f"*32))


def test_supported_claim_requires_separate_assessment():
    with pytest.raises(ValidationError, match="SUPPORT_ASSESSMENT_MISSING"):
        Claim(claim_id="c", kind="numeric_result", assertion="Improves F1",
              origin_type="author_result", support_status="supported")
    assessment = SupportAssessment(decision="supported", method="human",
                                   evaluator_id="reviewer_1", policy_version="v1",
                                   rationale="Compared quote")
    with pytest.raises(ValidationError, match="SUPPORTED_WITHOUT_EVIDENCE"):
        Claim(claim_id="c", kind="numeric_result", assertion="Improves F1",
              origin_type="author_result", support_status="supported",
              assessment=assessment)


def test_knowledge_cross_references_and_status_gate():
    doc = make_doc()
    ref = resolve_evidence_candidate(doc, proposal())
    review = SupportAssessment(decision="supported", method="human",
        evaluator_id="reviewer_1", policy_version="v1", evidence_ids=(ref.evidence_id,),
        rationale="Verified source quote")
    claim = Claim(claim_id="c", kind="numeric_result", assertion="F1 rises to 0.84",
                  origin_type="author_result", support_status="supported",
                  evidence_ids=(ref.evidence_id,), assessment=review)
    node = MindNode(node_id="n", node_type="paper", title="Paper",
                    status="verified", claim_ids=("c",))
    report = validate_knowledge_references(doc, node, [claim], [ref])
    assert (report.claim_count, report.anchor_count, report.node_count) == (1, 1, 1)
    fake = claim.model_copy(update={"support_status": "candidate", "assessment": None})
    with pytest.raises(DomainValidationError, match="NODE_FALSE_VERIFIED"):
        validate_knowledge_references(doc, node, [fake], [ref])


def test_orphan_claim_and_invalid_evidence_id():
    doc = make_doc()
    claim = Claim(claim_id="c", kind="other", assertion="x", origin_type="background",
                  evidence_ids=("missing",))
    node = MindNode(node_id="n", node_type="paper", title="Paper", claim_ids=("c",))
    with pytest.raises(DomainValidationError, match="CLAIM_EVIDENCE_MISSING"):
        validate_knowledge_references(doc, node, [claim], [])
    unlinked = Claim(claim_id="orphan", kind="other", assertion="x", origin_type="background")
    with pytest.raises(DomainValidationError, match="ORPHAN_CLAIM"):
        validate_knowledge_references(doc, MindNode(node_id="n", node_type="paper", title="Paper"),
                                      [unlinked], [])


def test_legacy_never_fabricates_verified_evidence_and_is_stable():
    old = {"name": "Paper", "status": "verified", "claim_ids": ["fake"],
           "children": [{"name": "Methods", "description": "A"},
                        {"name": "Methods", "description": "B"}]}
    node = adapt_legacy_tree(old, REV)
    assert node.status == "legacy_unverified"
    assert node.claim_ids == ()
    assert node.children[0].node_id != node.children[1].node_id
    assert all(c.status == "legacy_unverified" for c in node.children)
    assert canonical_serialize(node) == canonical_serialize(adapt_legacy_tree(old, REV))


def test_legacy_cycle_and_bad_children():
    node = {"name": "root"}
    node["children"] = [node]
    with pytest.raises(ValueError, match="LEGACY_CYCLE"):
        adapt_legacy_tree(node, REV)
    with pytest.raises(ValueError, match="LEGACY_CHILDREN_INVALID"):
        adapt_legacy_tree({"name": "root", "children": {"attached": []}}, REV)


def test_schema_export_and_untyped_serialization_rejected(tmp_path):
    node = adapt_legacy_tree({"id": "x", "title": "Conclusions",
                              "notes_text": "Unverified", "children": []}, REV)
    assert node.summary == "Unverified"
    paths = export_schemas(tmp_path)
    assert len(paths) == len(SCHEMAS) == 7
    for path in paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        # Recursive MindNode exports a legal top-level $ref to $defs.
        actual = schema
        if "$ref" in actual:
            assert actual["$ref"].startswith("#/$defs/")
            actual = schema["$defs"][actual["$ref"].split("/")[-1]]
        assert "properties" in actual
        assert actual["additionalProperties"] is False
    with pytest.raises(TypeError):
        canonical_serialize({"raw": "dict"})


def test_untrusted_claim_candidate_cannot_self_attest_verified():
    with pytest.raises(ValidationError):
        ClaimCandidate(candidate_id="c1", revision_id=REV, kind="numeric_result",
            assertion="F1 improves", origin_type="author_result",
            evidence_candidates=(proposal(),), support_status="supported")
    with pytest.raises(ValidationError, match="CLAIM_ABSTAIN_REASON_REQUIRED"):
        ClaimCandidate(candidate_id="c1", revision_id=REV, kind="other",
            assertion="Claim without sources", origin_type="unknown")
    doc = make_doc()
    original = proposal()
    raw = ClaimCandidate(candidate_id="c1", revision_id=REV, kind="numeric_result",
        assertion="F1 improves", origin_type="author_result",
        evidence_candidates=(original,), core_claim=True)
    anchor = resolve_evidence_candidate(doc, original)
    claim = promote_claim_candidate(doc, raw, [anchor])
    assert claim.support_status == "candidate"
    assert claim.assessment is None
    assert claim.evidence_ids == (anchor.evidence_id,)
    without_evidence = promote_claim_candidate(doc, raw, [])
    assert without_evidence.support_status == "unverified"
    with pytest.raises(DomainValidationError, match="CANDIDATE_EVIDENCE_MISMATCH"):
        unrelated = resolve_evidence_candidate(doc, proposal("Résumé"))
        promote_claim_candidate(doc, raw, [unrelated])
