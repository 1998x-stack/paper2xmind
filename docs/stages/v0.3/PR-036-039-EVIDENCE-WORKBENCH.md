# PR-036–039 · Evidence Workbench — integrated V0.3 delivery

This is the *one final stacked PR* covering versioned evidence persistence,
authenticated publishing and review, the React evidence inspector, independent
golden evaluation and CI release gates. Base branch:
feat/v0.3-pr035-evidence-verification (PR #7). It must be reviewed/merged in
stack order after PR #1–#7; no automatic merge into main is performed.

## Engineering scope

| Previous stage | Delivered together in this PR |
|---|---|
| PR-036 Durable Evidence Artifacts | SQLite additive schema, revision/source SHA check, immutable artifact BLOBs, two-phase stage/publish, optional append-only claims enrichment, atomic signed review state and event log, optimistic review ETag |
| PR-037 Evidence Inspector | Accessible browser tab with source quote, PDF page, Block and Unicode offsets, candidate status, warning/conflict list, reviewer rationale and signed review form |
| PR-038 Independent Evaluation | Synthetic PDF integration fixture + independently curated rights-noted paper/claim/review evaluators inherited from PR-032/033/034/035; false-positive/negative and source hashes explicit |
| PR-039 Release Gates | Python 3.10/3.11/3.12 full core and backend matrix, Vite production build, schema export, adversarial API tests, feature-gated rollout and safe rollback docs |

## Architecture and authenticity boundaries

    V0.2 ready revision (source.pdf, source_sha256 in revisions table)
                  |
        OFF by default: P2X_EVIDENCE_ENABLED=1
                  |
       StructuredPDFBlockParser (offline)
                  ↓
        DocumentIR + ChunkManifest
                  ↓
       atomic stage + publish (SQLite)
                  |
    optional separate PR-034 extraction (explicit model opt-in only)
                  ↓
       append-only ClaimExtractionLedger + reproducible ReviewAnalysis
                  ↓
     /api/evidence/papers/... (role-bound bearer authentication)
                  ↓
         React Evidence Inspector (candidate, quote, risk)
                  ↓
     authorized human reviewer writes rationale & decision
                  ↓
       server-held HMAC ReviewEnvelope, immutable nonce, audit chain
                  ↓
       independent validate_review_outcome on EACH authenticated API read
                  ↓
       ReviewOutcome (separate, versioned; PR-034 ledger unmodified)

A valid quote position alone does not entail scientific correctness. Heuristic
risk signals are not evidence that a claim is supported; only a recognized
external reviewer may sign a decision. HMAC attests to a backend-held key, not
to an actual human's scientific diligence, real-world identity or independence.
No actual human research-paper review was performed during this development.

### Database schema

Additive tables in the EXISTING v0.2 data/paper2xmind.sqlite3:

- evidence_bundles: revision ID, paper ID, PDF hash, STAGED/PUBLISHED,
  versioned bundle hash, created/published timestamps.
- evidence_artifacts: (revision,kind) PK, SHA-256 and original canonical JSON BLOB;
  kinds document_ir, chunks, claims, review_analysis, each inserted once.
- evidence_review_events: reviewer ID, globally unique (reviewer_id,nonce),
  one decision per (revision_id,claim_id), source request fingerprint,
  signed envelope, timestamp.
- evidence_review_state: latest separate ReviewOutcome blob, digest,
  optimistic version; rebuilt and verified against signed reviews.
- evidence_audit_log: append-only *application-level* per-revision hash chain,
  stage/publish/claim enrichment/review events.

Each artifact SHA and the bundle-set SHA are checked on publication and reads.
Signed review outcomes are independently checked against trusted HMAC keys on
API reads, not just against mutable database hashes.

**Important**: an operator with direct database write access can potentially
rewrite the log and all derived hashes. This is NOT an externally sealed/WORM
audit trail. For production compliance, replicate chain anchors to an
externally immutable audit system; introduce backups, disaster recovery,
multi-node locking design and key rotation protocols.

### Revision lifecycle

Source PDF hash in the v0.2 revisions table and the physical
papers/{paper_id}/source.pdf MUST match DocumentIR.pdf_sha256. The revision
must already be READY. Stage validates DocumentIR/ChunkManifest and optional
PR-034 ClaimExtractionLedger, then derives PR-035 ReviewAnalysis itself.

STAGED is not visible through ordinary GET. A separate explicit PUBLISH
transaction rechecks the hashes and freezes the artifact set. Importer may
append a claims/analysis pair **once** to a published source-only baseline
using optimistic expected_bundle_hash. The original DocumentIR/chunks are
never rewritten. Subsequent candidates cannot overwrite published claims.
Adding a future extraction version requires a *new* paper revision or an
explicit schema revision, not an in-place replacement.

Signed review decisions are separate from immutable candidates. Each review
requires the exact latest expected_outcome_sha256 (or null for first decision).
Concurrent stale writes fail with HTTP 409. The same reviewer+nonce+request is
idempotent; a reused nonce with a different request is a conflict. Durable
SQLite uniqueness provides protection across process restarts. There is no
automatic background retry, no external LLM invocation and no claim of
distributed database correctness.

## Safe configuration and rollout

**ALL NEW V0.3 EVIDENCE FEATURES ARE DISABLED BY DEFAULT**.

Set server-side only:

- P2X_EVIDENCE_ENABLED=1 — enables the evidence API routes.
- P2X_EVIDENCE_AUTOSTAGE=1 — optional source-only DocumentIR/Chunk
  publication after the old Worker has already marked a paper READY.
  Requires P2X_EVIDENCE_ENABLED=1 as well.
- P2X_EVIDENCE_AUTH_JSON — server environment JSON object keyed by actor ID.
  Each actor carries token_sha256, roles, and optionally review_key_hex.
  Never put raw tokens or signing keys into frontend bundles, code, logs or
  user-provided PDFs.

The registry format (placeholders, NOT real credentials):

    {
      "importer-operator": {
        "token_sha256": "64-lowercase-hex-of-secret-operator-bearer-token",
        "roles": ["importer", "viewer"]
      },
      "independent-reviewer": {
        "token_sha256": "64-lowercase-hex-of-a-different-random-token",
        "roles": ["viewer", "reviewer"],
        "review_key_hex": "at-least-32-random-bytes-encoded-as-lowercase-hex",
        "allowed_verdicts": [
          "supported", "unsupported", "ambiguous", "contradicted"
        ]
      }
    }

Generate independent cryptographically random token/key material outside the
repository, put only each token's SHA-256 digest and server-side review key
hex in server configuration. The reviewer signs ONLY on the backend.
Run behind a trusted reverse proxy with TLS, authentication isolation,
request-size limits, access logging that redacts Authorization, and network
policy. If authorization is misconfigured, the API must fail closed.
The browser prompts for an access token and keeps it in component memory,
not persistent localStorage. It must not be opened to untrusted origins.

Existing V0.2 paper browsing/legacy chat routes retain their old behavior.
This PR does NOT retrofit comprehensive authentication on unrelated legacy
API paths. New evidence API security is therefore a new-surface boundary,
not a statement that the entire v0.2 platform is multitenant-ready.

## HTTP contracts

All routes require P2X_EVIDENCE_ENABLED=1 and:

    Authorization: Bearer <random-server-registered-token>

Prefix: /api/evidence/papers

| Method | Path suffix | Required role |
|---|---|---|
| POST | /{paper_id}/revisions/{revision_id}/stage | importer |
| POST | /{paper_id}/revisions/{revision_id}/publish | importer |
| POST | /{paper_id}/revisions/{revision_id}/enrich | importer |
| GET | /{paper_id}/latest | viewer |
| GET | /{paper_id}/revisions/{revision_id} | viewer |
| POST | /{paper_id}/revisions/{revision_id}/reviews | reviewer |
| GET | /{paper_id}/revisions/{revision_id}/audit | admin |

Stage body:
    {"document":<DocumentIR JSON>, "chunks":<ChunkManifest JSON>,
     "claims":<ClaimExtractionLedger JSON or null>}

Append claims to published baseline:
    {"claims":<ClaimExtractionLedger JSON>,
     "expected_bundle_hash":"<current immutable-source bundle version SHA>"}

Review:
    {
      "claim_id":"claim_...",
      "verdict":"ambiguous",
      "rationale":"I checked the quoted source and need more context.",
      "nonce":"random-unique-request-id-at-least-16-chars",
      "expected_outcome_sha256":null
    }

Review decisions are signed on the server with the actor's server-configured
reviewer key. A human reviewer MUST inspect the actual original PDF,
experimental context and relevant evidence independently. The UI does not
display or accept a reviewer signing key. Model-generated text cannot become
a signed review by itself. A "supported" verdict is prohibited when PR-035
blocking risks or unresolved numeric conflict signals remain.

HTTP 401 means unauthenticated; 403 forbidden role; 404 disabled/not found;
409 stale/incompatible state; 422 invalid source, review policy or signature.

## Frontend UX and scope

- Preserve the existing Mind map and Chat interfaces.
- Add Evidence inspector tab. Source is loaded only with an authorized token.
- Show candidate assertion, status, source quoted text, block ID, page and
  Unicode half-open start/end offsets, risk signals and potential conflict.
- Explicitly state: no screening warning does not imply scientific support.
- Human reviewer form with decision and required explanation, server writes
  signature, browser shows success only after HTTP acknowledgement.
- Paginate/keyword filter claims for large collections. No HTML insertion
  with innerHTML, no storing credentials in localStorage.
- State reset on paper change, and stale asynchronous source reads discarded.

This is a functional reviewer inspector, NOT a character-accurate PDF
highlight renderer, arbitrary visual side-by-side PDF diff, complete
scientific table-cell comparator, or production identity provider.
Those are different optional engineering enhancements.

## Worker integration and fallback

When both flags enabled, the already successful V0.2 worker may *optionally*
generate DocumentIR + ChunkManifest offline from its stored PDF and publish
a source-only baseline. It never calls a new model automatically.
If this optional post-processing fails, it logs the exception and leaves
the original V0.2 READY status and XMind file unchanged.

An operator can later run the PR-034 explicit extraction CLI (offline
fixture or authorized model endpoint), then POST the validated claim
ledger through the append-only /enrich endpoint. The backend derives the
screening report from the trusted ledger; no model may upload a fabricated
ReviewAnalysis or supported verdict through /stage or /enrich.

## Testing and acceptance criteria

Synthetic generated source PDF is parsed using real PyMuPDF; the
DocumentIR→ChunkManifest→FixtureClaimModel→Ledger→SQLite staging→publication
→authenticated reviewer signature→read-back runs without network or LLM.

The CI checks include:
- complete legacy core and backend regression suites on Python 3.10/3.11/3.12;
- Vite TypeScript production build;
- actual Chromium Playwright browser E2E of the evidence inspector using
  deliberately mocked HTTP responses (access denial, exact source rendering,
  review request fields and UI acknowledgement); this verifies browser
  behavior, NOT the server's reviewer identity or live PDF semantics;
- schema export and Python compilation;
- immutable staged artifact conflict, publish idempotency and SHA readback;
- append-once claims and optimistic bundle version CAS;
- admin/viewer/importer/reviewer HTTP authorization and disabled-by-default;
- duplicate nonce idempotency and changed-request rejection;
- stale review ETag, reviewer HMAC and signed result tampering;
- audit chain detection of edits;
- optional worker source-only publication with both flags enabled;
- previous PR-032–035 independently curated corpus evaluator tests.

Real-model extraction/semantic accuracy, real human review, browser E2E
against a live authenticated backend, and operational canary/backup/restore/
hostile-network testing were not performed. None should be presented as passing simply because CI is green.

## Release / rollback sequence

1. Merge stacked PRs in order; do not merge this directly into main ahead of
   its PR-035 parent. Confirm CI on the resulting merge commit.
2. Back up the v0.2 SQLite DB, PDF source files and XMind artifacts.
3. Deploy with both new flags off; verify legacy upload→XMind.
4. Provision distinct private importer and reviewer credentials, TLS,
   proxy request limits, operator authentication and secret rotation.
5. Enable P2X_EVIDENCE_ENABLED=1 for authorized local staging/review only;
   keep AUTOSTAGE off until parser CPU/RAM budget is measured.
6. Test synthetic ready revision, signed review, restart/read-back, audit,
   stale-lock and rollback cases in the deployment environment.
7. Enable AUTOSTAGE for a limited cohort only after measuring latency and
   storage. Monitor review nonce conflicts, signature failures and source
   parsing errors.
8. Roll back by setting both flags to 0. Legacy V0.2 keeps running.
   The additive SQLite tables remain intact; disabling is non-destructive.
   Do NOT drop tables or delete review evidence as routine rollback.

## Evidence maturity

**Engineering-complete in synthetic CI** is not equivalent to production
security certification or scientific truth. A valid HMAC proves key possession,
not reviewer independence or actual study verification. A source quote proves
existence, not logical entailment. A rights note in a benchmark is curator-
reported metadata, not external legal permission verification.

Follow-up after this merged PR should be operational verification and
real independently licensed annotated corpus evaluation, not additional
unnecessary architectural feature stages.
