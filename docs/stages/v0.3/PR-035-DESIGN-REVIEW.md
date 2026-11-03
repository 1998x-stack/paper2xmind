# V0.3 PR-035 — Evidence Verification & Claim Reconciliation

## Baseline and scope

Stacked on feat/v0.3-pr034-grounded-claims. Does not modify V0.2 Worker,
HTTP API, SQLite schema, React UI, XMind export or main. Introduces only
versioned independent source-risk analysis and externally signed review records.

**Essential distinction:** an exact quote at an existing PDF location does not
prove scientific semantic entailment. PR-034 verifies source location;
PR-035 detects selected source/claim inconsistencies and preserves a trusted
external review record. Neither an LLM nor lexical checking automatically
asserts that an academic claim is correct.

## Design

    DocumentIR + ChunkManifest + ClaimExtractionLedger
       ↓ independent validate_extraction_ledger (before analysis)
    ReviewAnalysis
       ├── NUMERIC_NOT_IN_EVIDENCE (blocking review signal)
       ├── UNIT_NOT_IN_EVIDENCE (blocking review signal)
       ├── ORIGIN_PRIOR_WORK_RISK (review signal)
       ├── ORIGIN_AUTHORSHIP_RISK (review signal)
       ├── DATASET_CONTEXT_MISSING (review signal)
       ├── POLARITY_RISK (review signal)
       └── PotentialConflict: same statement skeleton/section,
           different numbers from different exact source anchors
       ↓ external authenticated human review (not included in repo)
    ReviewEnvelope bound to PDF/ledger/analysis/claim/evidence SHA
       ↓ trusted external reviewer HMAC-SHA256 key and allowed verdict
    SignedReview
       ↓ independent verification / source and role reconciliation
    ReviewOutcome (reviewed claims, decisions, outstanding candidates)

No automatic LLM-to-supported transition. Missing reviews leave claims as
candidate. A false numeric anchor or unresolved potential conflict prevents a
supported verdict under the current policy; unsupported/ambiguous still
require a signed reviewer.

## Deep Review — critical decisions

1. **Citation existence is not logical entailment.** Numerical and unit checks
   compare lexical Decimal values and common units in the proposition and
   quoted EvidenceRef(s). They catch obvious added or changed measurements.
   They do not prove the correct metric, denominator, p-value, experimental
   condition, confidence interval or source attribution. A matching value
   does not imply verification; a mismatched value is a blocking risk.

2. **Author contribution versus cited prior work.** Source cues such as
   "prior studies" and "we propose" are only screening patterns. Absence of a
   warning cannot establish attribution truth. Real reviewers must inspect
   the original text, references and surrounding paper.

3. **Conflict detection is deliberately conservative.** Pairs with the same
   claim kind, origin, section and number-stripped assertion, but different
   numbers and different evidence IDs, create PotentialConflict only.
   Different experiments, datasets or baselines may explain the difference.
   The implementation never automatically marks either claim contradicted.

4. **Reviewer trust cannot be delegated to the model.** ReviewAuthority holds
   externally supplied reviewer keys and allowed verdict permissions. Keys
   never enter models/prompts/reports. The signed envelope binds exact PDF
   SHA-256, PR-034 ledger digest, PR-035 analysis digest, candidate claim
   digest, complete evidence ID set, reviewer, rationale, timestamp and nonce.
   Reviewer identity equal to extraction model ID is blocked.

5. **HMAC is integrity, not proof of human work.** A valid HMAC demonstrates
   key possession but not that an individual read a PDF or that the verdict
   is factually correct. This PR has no authenticated human-review UI,
   persistent reviewer ACL, external secrets manager integration, durable
   replay/nonce database, key rotation/revocation history or asymmetric
   signature. Nonce checks are in-batch only, NOT global replay prevention.
   A production service must supply these in PR-036+.

6. **Review artifact is independently revalidated.** Re-run upstream source
   and chunk checks, recompute deterministic screening and verify signature
   before reconstructing the exact expected reviewed claims. Imported JSON
   cannot set supported by changing a Pydantic field; canonical digests of
   reconstituted outcome must equal stored outcome. The original PR-034
   candidate ledger is immutable.

7. **Limitations remain explicit.** Arabic-number/units matching is a narrow
   lexical guard, not an algebra engine, statistical interpretation model,
   multilingual academic entailment checker, table-cell verifier or formula
   reconstruction system.

## Review schemas

- ReviewAnalysis / claim_review/1.0.0: source digests, policy_version,
  ordered claim IDs, screening signals and potential conflicting pairs.
- ReviewEnvelope: reviewer ID, decision, rationale, exact evidence IDs,
  source/claim/analysis digests, timestamp and nonce.
- SignedReview: HMAC-SHA256 over canonical envelope JSON.
- ReviewOutcome: signed reviews, separately assessed Claim records,
  outstanding Claim IDs, source digests. Never write these final states into
  the model-controlled ClaimExtractionLedger.

All Pydantic schemas can be exported via:

    python -m paper2xmind.review.export_schema schemas/generated/v0.3/review

## Offline analysis

    python -m paper2xmind.review \
      --document output/paper.document-ir.json \
      --chunks output/paper.chunks.json \
      --claims output/paper.claim-candidates.json \
      --output output/paper.review-analysis.json

This CLI never performs a human review or contacts an LLM. Signed review is
only a library integration contract for a separate trusted review host.
The HMAC signing key must come from a secure caller-managed facility, never
the repository, frontend, model or an untrusted document.

## Independent evaluation

The offline benchmark at evals/benchmarks/review_groundtruth_v035.py accepts a
rights-noted local manifest with source SHA-256 for DocumentIR, chunks and
PR-034 extraction ledger. Every candidate requires a separately supplied
gold verdict with annotator and rationale; missing/duplicate gold labels
invalidate the evaluation instead of shrinking its denominator.

- negative_flag_recall: externally unsupported/contradicted candidates with
  at least one risk signal / all externally unsupported/contradicted.
- supported_flag_rate: externally supported candidates with risk signals /
  all externally supported.
- flagged_claims and potential_conflicts.

These are screening measurements; they do not by themselves validate truth,
and the provided annotator metadata does not prove real identity or rights.
Default CI includes synthetic test claims only. No real independently
labeled licensed paper collection was provided, and no actual human review
was executed in this code development task.

## Acceptance and rollback

- Python 3.10/3.11/3.12: existing Core, Backend, frontend regression tests.
- Evidence correctness is inherited from independently validated PR-034.
- Numeric/unit/author/prior-work/dataset/polarity risk unit tests.
- False numeric conflict remains only a potential conflict.
- Unsigned candidate remains candidate; signed synthetic review yields
  separately assessed Claim object without mutating extraction ledger.
- Wrong/revoked key, invalid signature, stale source, forged review identity,
  duplicate decision, future timestamp and altered outcome fail closed.
- Human label coverage, rights metadata, source SHA and path traversal tested.
- CLI produces only screening risk report; no partial artifact on failure.
- No database migrations, HTTP changes or Worker changes; rollback is simply
  dropping this stacked PR.

## Next stage: PR-036

Revisioned Evidence Artifacts & Controlled Review API:
SQLite migrations, versioned content hashes, authenticated human-review
workflow, external secret-manager integration, durable nonce replay index,
append-only audit records, atomic staged publication, read-back verification,
worker rollout flag and explicit rollback. Only then consider a production
human-reviewed source-grounded XMind UI.
