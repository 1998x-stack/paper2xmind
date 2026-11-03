# V0.4 PH-00/01/02 — Code Review and Design Record

## Baseline and delivery

Repo: 1998x-stack/paper2xmind.
Prerequisite: V0.3 integration PR #9 (main currently contains V0.2 but
the final V0.3 branch is not yet on main).
Implementation branch: feat/v0.4-ph00-02-product-foundation.

This phase is a functional code change, not simply a proposal. It adds
real public-private API isolation, a synthetic original PDF demo and a
new immutable domain ResearchMap. It does not implement all PH-03..08
work such as glyph-level PDF alignment, general-user PDF processing,
rearrangement/version history or public link sharing.

## PH-00 security before public deployment

Files:
- backend/app/security/private_api.py — route-level public/private gate
- backend/app/main.py — middleware and worker opt-in in public mode
- backend/tests/conftest.py — explicit local compatibility for V0.2 tests
- backend/tests/test_public_demo_v04.py — role and boundary goldens

Default P2X_DEPLOYMENT_MODE=public. The only anonymous API prefix is
/api/public/demos; it is additionally disabled unless
P2X_PUBLIC_DEMO_ENABLED=1. The complete private legacy /api namespace
is protected by an explicit admin token from P2X_EVIDENCE_AUTH_JSON.
Legacy data is global single-workspace data, so simply granting a viewer
role is insufficient protection for a public multi-user service.
The existing /api/evidence paths retain their independent role gate.
Unknown /api paths are not accidentally exposed. Invalid settings fail
closed. Public-demo responses contain original teaching data only.

P2X_DEPLOYMENT_MODE=local is a localhost-only opt-in. Never expose it to
the internet. Public worker remains off unless the operator explicitly
sets P2X_ALLOW_PRIVATE_WORKER=1.

This is not production multi-tenant authorization, formal identity
federation or an external tamper-resistant audit service.

## PH-01 no-login zero-provider demo

Files:
- backend/app/services/demo_catalog.py
- backend/app/api/public_demos.py
- frontend/src/features/demo/PublicDemoPage.tsx
- frontend/src/App.tsx, frontend/src/vite-env.d.ts
- frontend/e2e/demo.spec.ts
- backend/tests/test_public_demo_v04.py

The demo PDF is programmatically authored inside this project, not
downloaded from a publisher. It is deterministic and explicitly labeled
fictional. Its four proposed candidate claims cite original source text
using the regular PR-031/033/034 exact source offset validation.
The PR-034 model provider is FixtureClaimModel only; OpenAI-compatible
providers, private SQLite and user uploads are never called.

The Vite UI has /demo as a standalone route; VITE_PUBLIC_LANDING=1
optionally makes it the public home page. It shows PDF preview, map and
outline, a source-inspector panel, exact Unicode offsets, provenance and
the difference between source-location validity and scientific support.
It does NOT advertise PDF glyph-level highlights. No account registration,
token or private workspace source is required.

The user journey is: load original teaching PDF → pick a finding → inspect
original excerpt → open cited PDF page → switch map/outline without losing
selection. The two views reuse the identical ResearchMap identity.

## PH-02 ResearchMap Domain

Files:
- paper2xmind/research_map/contracts.py
- paper2xmind/research_map/projector.py
- backend/app/api/research_maps.py
- tests/test_research_map_v04.py
- backend/tests/test_research_api_v04.py

Canonical source trust path:
  DocumentIR + ChunkManifest + ClaimExtractionLedger
         ↓ independently validate_extraction_ledger
  optional trusted ReviewOutcome + ReviewAuthority + ReviewAnalysis
         ↓ independently validate_review_outcome / signature / sources
  deterministic ResearchMap (root/group/claim nodes, source-linked edges)

ResearchMap is a read projection, not another writable place to store
facts or scientific reviewer authority. Node IDs derive from the PDF
revision and stable claim ID, independent of the node title or UI layout.
All evidence IDs must exist in the original ledger. The model cannot
set review_status; without trusted ReviewOutcome the map remains
candidate/unverified. The typed graph validator rejects duplicates,
dangling references and invalid parent links, and a separate validator
can reproject/re-hash the entire map from the original source.

Private API:
  GET /api/research/papers/{paper_id}/maps/latest

It requires both evidence and map feature flags. In public mode the
legacy-private gate additionally requires an admin token. A source-only
bundle returns 409, not an invented research map. Verified claims are
projected only after original HMAC-based PR-035 outcome validation.

## Test and acceptance

- Python 3.10, 3.11 and 3.12: core, prior V0.3 and backend tests.
- Runtime-generated original PDF hash matches source and all source
  offsets; no fake PDF names or nonexistent citations accepted.
- Anonymous cannot list/upload/download any legacy private resources.
- Viewer role cannot bypass admin-only legacy gate.
- Invalid or missing token registry fails closed.
- Safe-default deployment mode rejects private anonymous access.
- No anonymous OpenAI-compatible provider calls.
- Map graph and IDs deterministic across runs and review revisions.
- Forged supported status, invalid reviewer signature, stale source or
  dangling evidence rejects independent validation.
- Chromium uses mocked HTTP for frontend behavior; backend TestClient
  separately validates the actual parser and authorization API.

## Next engineering gates

PH-03: accurate PDF glyph-level localization with repeated-text,
rotation and two-column goldens, plus fail-closed block/page fallback.
PH-04: interactive zoomable graph and Outline synchronized to the
same selected node and evidence.
PH-05: user-upload pipeline, explicit status and resumability.
PH-06: Reviewable map revisions, preview/diff/undo.
PH-07: original-rights-aware, explicitly opted-in redacted sharing.
PH-08: real licensed paper corpus + external human evaluation and
Product Hunt usability/activation/retention gates.

Never treat a passing software test as evidence that a scientific
claim is semantically supported or a public deployment is fully secure.
