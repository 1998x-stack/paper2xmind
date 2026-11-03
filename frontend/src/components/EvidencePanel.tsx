import React from 'react'

/** V0.3 evidence workbench. Token is kept only in component memory. */
type Claim = {
  claim_id: string
  kind: string
  assertion: string
  support_status: string
  origin_type: string
  evidence_ids: string[]
  assessment?: { rationale: string; evaluator_id: string; method: string } | null
}
type EvidenceRef = {
  evidence_id: string
  block_id: string
  page_index: number
  start_cp: number
  end_cp: number
  quote: string
}
type Signal = { claim_id: string; code: string; severity: 'block' | 'review' }
type Conflict = { left_claim_id: string; right_claim_id: string; reason: string }
type EvidenceBundle = {
  revision_id: string
  pdf_sha256: string
  state: string
  bundle_hash: string
  review_outcome_sha256: string | null
  review_outcome: { claims: Claim[] } | null
  documents: {
    document_ir: { blocks: { block_id: string; text: string; page_index: number }[] }
    claims?: { claims: Claim[]; evidence: EvidenceRef[] }
    review_analysis?: { signals: Signal[]; potential_conflicts: Conflict[] }
  }
}

type Props = { paperId: string }

const PAGE_SIZE = 20

export const EvidencePanel: React.FC<Props> = ({ paperId }) => {
  const [token, setToken] = React.useState('')
  const requestVersion = React.useRef(0)
  const [bundle, setBundle] = React.useState<EvidenceBundle | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState('')
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [filter, setFilter] = React.useState('')
  const [page, setPage] = React.useState(0)
  const [verdict, setVerdict] = React.useState('ambiguous')
  const [rationale, setRationale] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [feedback, setFeedback] = React.useState('')

  // Never carry private evidence or credentials from one paper to another.
  React.useEffect(() => {
    requestVersion.current += 1
    setToken('')
    setBundle(null)
    setSelectedId(null)
    setError('')
    setRationale('')
    setFeedback('')
    setFilter('')
    setPage(0)
  }, [paperId])

  const getEvidence = async (signal?: AbortSignal) => {
    const version = ++requestVersion.current
    if (!token.trim()) {
      setError('Enter an authorized evidence access token.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await fetch(
        '/api/evidence/papers/' + encodeURIComponent(paperId) + '/latest',
        { headers: { Authorization: 'Bearer ' + token }, signal, cache: 'no-store' }
      )
      if (!response.ok) {
        throw new Error(response.status === 404
          ? 'No published evidence is available, or the feature is disabled.'
          : 'Evidence access failed (' + response.status + ').')
      }
      const next = await response.json() as EvidenceBundle
      if (!signal?.aborted && version === requestVersion.current) {
        setBundle(next)
        setSelectedId(null)
        setPage(0)
        setFeedback('')
      }
    } catch (err) {
      if (!signal?.aborted && version === requestVersion.current) setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      if (!signal?.aborted && version === requestVersion.current) setLoading(false)
    }
  }

  const candidates = bundle?.review_outcome?.claims
    ?? bundle?.documents.claims?.claims ?? []
  const evidence = new Map((bundle?.documents.claims?.evidence ?? [])
    .map(ref => [ref.evidence_id, ref]))
  const analysis = bundle?.documents.review_analysis
  const normalizedFilter = filter.trim().toLocaleLowerCase()
  const filtered = candidates.filter(c => (
    c.assertion.toLocaleLowerCase().includes(normalizedFilter)
    || c.kind.toLocaleLowerCase().includes(normalizedFilter)
    || c.support_status.toLocaleLowerCase().includes(normalizedFilter)
  ))
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const active = candidates.find(c => c.claim_id === selectedId)
    ?? (selectedId === null ? candidates[0] : undefined)

  const sendReview = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!bundle || !active || rationale.trim().length < 10) return
    setSubmitting(true)
    setFeedback('')
    setError('')
    try {
      const response = await fetch(
        '/api/evidence/papers/' + encodeURIComponent(paperId)
        + '/revisions/' + encodeURIComponent(bundle.revision_id) + '/reviews',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer ' + token,
          },
          body: JSON.stringify({
            claim_id: active.claim_id,
            verdict,
            rationale: rationale.trim(),
            nonce: crypto.randomUUID() + '-review',
            expected_outcome_sha256: bundle.review_outcome_sha256,
          }),
        },
      )
      if (!response.ok) {
        if (response.status === 409) throw new Error('Review changed: reload evidence and retry.')
        if (response.status === 403) throw new Error('This account has no reviewer permission.')
        throw new Error('Review was not accepted (' + response.status + ').')
      }
      const updated = await response.json() as EvidenceBundle
      setBundle(updated)
      setFeedback('Review saved and bound to this evidence revision.')
      setRationale('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review failed')
    } finally {
      setSubmitting(false)
    }
  }

  return <section className="h-full overflow-auto p-4 max-w-6xl mx-auto" aria-label="Evidence workbench">
    <header className="mb-4 space-y-2">
      <h1 className="text-xl font-semibold">Evidence inspector</h1>
      <p className="text-sm text-gray-600">
        Candidate claims are not scientifically verified. Deterministic source
        checks are only screening signals; an authorized reviewer must assess meaning.
      </p>
      <label htmlFor="evidence-access-token" className="block text-sm font-medium">Evidence access token</label>
      <div className="flex gap-2 flex-wrap">
        <input id="evidence-access-token" type="password" autoComplete="off"
          className="border rounded px-3 py-2 min-w-0 flex-1"
          placeholder="Server-authorized token (not stored in browser storage)"
          value={token} onChange={event => setToken(event.target.value)} />
        <button type="button" onClick={() => { void getEvidence() }} disabled={loading}
          className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50">
          {loading ? 'Loading…' : 'Load evidence'}
        </button>
      </div>
      {error && <p className="text-red-700" role="alert">{error}</p>}
      {feedback && <p className="text-green-700" role="status">{feedback}</p>}
    </header>
    {bundle && <>
      <div className="border rounded p-3 mb-4 bg-gray-50 text-sm">
        <p><strong>Revision:</strong> <code className="break-all">{bundle.revision_id}</code></p>
        <p><strong>PDF SHA-256:</strong> <code className="break-all">{bundle.pdf_sha256}</code></p>
        <p><strong>Bundle:</strong> {bundle.state}, source fingerprint verified on publication.</p>
        {!bundle.documents.claims && <p className="text-amber-700 mt-1">
          No claim extraction is published for this revision. Source and chunk records can still be inspected.
        </p>}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 min-h-0">
        <nav className="lg:col-span-2 border rounded p-3 space-y-2" aria-label="Research claims">
          <div className="flex justify-between items-center">
            <h2 className="font-semibold">Claims ({candidates.length})</h2>
            <span className="text-xs text-gray-600">{analysis?.signals.length ?? 0} review signals</span>
          </div>
          <label htmlFor="claim-filter" className="block text-xs text-gray-600">Filter claims</label>
          <input id="claim-filter" value={filter} onChange={event => {
            setFilter(event.target.value); setPage(0)
          }} className="border rounded px-2 py-1 w-full" placeholder="Search assertions, status, type"/>
          <div className="space-y-1">
            {visible.length === 0 && <p className="text-sm text-gray-500">No matching candidates.</p>}
            {visible.map(claim => <button key={claim.claim_id} type="button"
              aria-current={active?.claim_id === claim.claim_id ? 'true' : undefined}
              className={'w-full text-left p-2 rounded border ' + (
                active?.claim_id === claim.claim_id
                  ? 'bg-blue-50 border-blue-400' : 'border-transparent hover:bg-gray-100'
              )}
              onClick={() => { setSelectedId(claim.claim_id); setRationale(''); setFeedback('') }}>
              <span className="block text-sm font-medium break-words">{claim.assertion}</span>
              <span className="text-xs text-gray-600">{claim.kind} · {claim.support_status}</span>
            </button>)}
          </div>
          <div className="flex items-center justify-between text-xs gap-2">
            <button type="button" disabled={page === 0} className="border px-2 py-1 rounded disabled:opacity-40"
              onClick={() => setPage(v => Math.max(0, v - 1))}>Previous</button>
            <span>Page {page + 1} / {Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))}</span>
            <button type="button" disabled={(page + 1) * PAGE_SIZE >= filtered.length}
              className="border px-2 py-1 rounded disabled:opacity-40"
              onClick={() => setPage(v => v + 1)}>Next</button>
          </div>
        </nav>
        <div className="lg:col-span-3 border rounded p-4 space-y-4">
          {!active ? <p className="text-gray-500">Select a candidate to inspect its evidence.</p> : <>
            <header>
              <h2 className="text-lg font-semibold">{active.assertion}</h2>
              <p className="text-sm text-gray-600">Origin: {active.origin_type} · Status: {active.support_status}</p>
            </header>
            <section>
              <h3 className="font-semibold mb-2">Exact quotations</h3>
              {active.evidence_ids.map(id => {
                const item = evidence.get(id)
                return <blockquote key={id} className="border-l-4 border-blue-200 pl-3 mb-3">
                  {item ? <>
                    <p className="text-sm whitespace-pre-wrap">{item.quote}</p>
                    <p className="text-xs text-gray-600 mt-1">
                      Page {item.page_index + 1} · {item.block_id} ·
                      offset {item.start_cp}–{item.end_cp}
                    </p>
                  </> : <p className="text-red-700 text-sm">Citation missing from published ledger.</p>}
                </blockquote>
              })}
            </section>
            <section aria-label="Review signals">
              <h3 className="font-semibold">Review signals</h3>
              <ul className="list-disc pl-5 text-sm">
                {(analysis?.signals.filter(s => s.claim_id === active.claim_id) ?? [])
                  .map((signal, index) => <li key={signal.code + index}>
                    {signal.code} ({signal.severity})
                  </li>)}
                {(analysis?.potential_conflicts.filter(c => c.left_claim_id === active.claim_id
                  || c.right_claim_id === active.claim_id) ?? [])
                  .map((conflict, index) => <li key={index}>
                    Possible conflict: {conflict.reason}
                  </li>)}
              </ul>
              {(analysis?.signals.filter(s => s.claim_id === active.claim_id).length ?? 0) === 0
                && <p className="text-xs text-gray-500 mt-1">
                  No deterministic flag does not establish semantic support.
                </p>}
            </section>
            {active.assessment && <section className="rounded border p-3 bg-gray-50">
              <h3 className="font-semibold">Recorded reviewer assessment</h3>
              <p className="text-sm">{active.assessment.rationale}</p>
              <p className="text-xs text-gray-600">Reviewer: {active.assessment.evaluator_id}</p>
            </section>}
            {active.support_status === 'candidate' && <form onSubmit={event => { void sendReview(event) }}
              className="border-t pt-3 space-y-2">
              <h3 className="font-semibold">Authorized human review</h3>
              <p className="text-xs text-gray-600">
                Submitting requires a reviewer token. The server signs and audits your decision;
                you must independently inspect the original PDF and relevant research context.
              </p>
              <label htmlFor="review-verdict" className="block text-sm">Review decision</label>
              <select id="review-verdict" value={verdict}
                onChange={event => setVerdict(event.target.value)}
                className="w-full border rounded p-2">
                <option value="ambiguous">Ambiguous / needs more context</option>
                <option value="supported">Supported after independent review</option>
                <option value="unsupported">Unsupported</option>
                <option value="contradicted">Contradicted</option>
              </select>
              <label htmlFor="review-rationale" className="block text-sm">Reasoning and checked context</label>
              <textarea id="review-rationale" value={rationale}
                onChange={event => setRationale(event.target.value)}
                minLength={10} required rows={4}
                className="w-full border rounded p-2"
                placeholder="Describe which original sources, conditions and figures you checked." />
              <button type="submit" disabled={submitting || rationale.trim().length < 10}
                className="bg-blue-600 text-white rounded px-3 py-2 disabled:opacity-50">
                {submitting ? 'Saving…' : 'Record signed review'}
              </button>
            </form>}
          </>}
        </div>
      </div>
    </>}
  </section>
}
