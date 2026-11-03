import React from 'react'

type MapNode = {
  node_id: string
  parent_id: string | null
  kind: string
  title: string
  claim_id: string | null
  evidence_ids: string[]
  source_status: 'anchored' | 'unanchored'
  review_status: string
  core_claim: boolean
}
type EvidenceRef = {
  evidence_id: string
  block_id: string
  page_index: number
  start_cp: number
  end_cp: number
  quote: string
}
type DemoBundle = {
  demo_id: string
  title: string
  source_kind: 'original_synthetic_pdf'
  rights: string
  disclaimer: string
  pdf_sha256: string
  source_pdf_url: string
  research_map: {
    root_id: string
    revision_id: string
    nodes: MapNode[]
    evidence: EvidenceRef[]
    contains_unreviewed_claims: boolean
  }
  source_blocks: {
    block_id: string
    page_index: number
    normalized_text: string
  }[]
}

function SourceQuote({ reference, bundle }: {
  reference: EvidenceRef
  bundle: DemoBundle
}) {
  const block = bundle.source_blocks.find(b => b.block_id === reference.block_id)
  if (!block) return <p className="text-red-700">Source block unavailable.</p>
  // Python offsets are Unicode code points, not JavaScript UTF-16 indices.
  const chars = Array.from(block.normalized_text)
  const match = chars.slice(reference.start_cp, reference.end_cp).join('')
  if (match !== reference.quote) {
    return <p className="text-red-700" role="alert">
      The source quotation differs from its saved location. Cannot highlight.
    </p>
  }
  return <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
    <p className="text-xs font-medium text-slate-500 mb-2">
      Page {reference.page_index + 1} · exact source text · {reference.block_id}
    </p>
    <p className="text-sm leading-7 text-slate-800 whitespace-pre-wrap break-words">
      {chars.slice(0, reference.start_cp).join('')}
      <mark className="rounded bg-amber-200 px-0.5 text-slate-900">
        {match}
      </mark>
      {chars.slice(reference.end_cp).join('')}
    </p>
  </div>
}

export const PublicDemoPage: React.FC = () => {
  const [bundle, setBundle] = React.useState<DemoBundle | null>(null)
  const [error, setError] = React.useState('')
  const [selected, setSelected] = React.useState<string | null>(null)
  const [view, setView] = React.useState<'map' | 'outline'>('map')

  React.useEffect(() => {
    const controller = new AbortController()
    fetch('/api/public/demos/synthetic-retrieval', {
      signal: controller.signal, cache: 'no-store',
    }).then(async response => {
      if (!response.ok) throw Error('The public sample is unavailable.')
      return await response.json() as DemoBundle
    }).then(data => {
      if (controller.signal.aborted) return
      setBundle(data)
      const firstFinding = data.research_map.nodes.find(n => n.kind === 'finding')
      const firstClaim = data.research_map.nodes.find(n => n.claim_id)
      setSelected(firstFinding?.node_id ?? firstClaim?.node_id ?? null)
    }).catch(cause => {
      if (!controller.signal.aborted) setError(
        cause instanceof Error ? cause.message : 'The public sample is unavailable.'
      )
    })
    return () => controller.abort()
  }, [])

  const allNodes = bundle?.research_map.nodes ?? []
  const groups = allNodes.filter(n => n.kind === 'group')
  const active = allNodes.find(n => n.node_id === selected)
  const refs = bundle?.research_map.evidence ?? []
  const activeRefs = active?.evidence_ids
    .map(id => refs.find(ref => ref.evidence_id === id))
    .filter((ref): ref is EvidenceRef => Boolean(ref)) ?? []
  const selectNode = (node: MapNode) => setSelected(node.node_id)

  return <div className="min-h-screen bg-slate-100 text-slate-900">
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto max-w-[1500px] px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-indigo-600 p-2.5 text-white font-black" aria-hidden="true">P</div>
          <div>
            <p className="font-bold tracking-tight text-lg">Paper2XMind</p>
            <p className="text-xs text-slate-500">Research maps that show their sources</p>
          </div>
        </div>
        <span className="rounded-full bg-amber-50 text-amber-800 px-3 py-1.5 text-xs font-medium">
          Original synthetic example · no registration or AI key
        </span>
      </div>
    </header>
    <main className="mx-auto max-w-[1500px] p-4 md:p-6 space-y-5">
      <section className="text-center pt-3 pb-2">
        <h1 className="text-2xl md:text-4xl tracking-tight font-bold">
          See the research. Inspect the evidence.
        </h1>
        <p className="mt-3 mx-auto max-w-3xl text-sm md:text-base text-slate-600">
          Explore a clickable research map and trace each claim back to its exact
          source passage. A real scholarly paper is not required for this tutorial.
        </p>
      </section>
      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-4 text-red-800">
        {error}
      </div>}
      {!bundle && !error && <p role="status" className="text-center p-10">
        Building the original example and validating its citations…
      </p>}
      {bundle && <>
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm">
          <strong>What this demonstrates:</strong> {bundle.disclaimer}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          <section className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between gap-2 mb-2">
              <h2 className="font-semibold">Original PDF</h2>
              <a href={bundle.source_pdf_url} target="_blank" rel="noreferrer"
                className="text-xs text-indigo-700 underline">Open PDF</a>
            </div>
            <p className="text-sm text-slate-600 mb-3">{bundle.title}</p>
            <iframe title="Original synthetic paper PDF" src={bundle.source_pdf_url + '#page=1'}
              className="h-[370px] w-full rounded-lg border border-slate-200 bg-white"/>
            <p className="mt-2 text-xs text-slate-500 break-all">
              PDF SHA-256: {bundle.pdf_sha256}
            </p>
          </section>
          <section className="lg:col-span-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
            aria-label="Interactive research map">
            <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
              <h2 className="font-semibold">Research map</h2>
              <div className="inline-flex rounded-lg bg-slate-100 p-1" role="group" aria-label="Research map view">
                {(['map', 'outline'] as const).map(mode =>
                  <button key={mode} type="button" aria-pressed={view === mode}
                    className={'rounded-md px-3 py-1.5 text-sm capitalize ' +
                      (view === mode ? 'bg-white font-semibold shadow-sm' : 'text-slate-600')}
                    onClick={() => setView(mode)}>{mode}</button>
                )}
              </div>
            </div>
            <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-center text-sm font-semibold mb-4">
              Fictional retrieval study
            </div>
            <div className={view === 'map'
              ? 'grid grid-cols-1 sm:grid-cols-2 gap-3'
              : 'space-y-3'}>
              {groups.map(group => {
                const children = allNodes.filter(n => n.parent_id === group.node_id)
                return <div key={group.node_id}
                  className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <h3 className="font-semibold text-xs uppercase tracking-wide text-slate-500 mb-2">
                    {group.title}
                  </h3>
                  <div className="space-y-2">
                    {children.map(node =>
                      <button key={node.node_id} type="button"
                        aria-pressed={active?.node_id === node.node_id}
                        onClick={() => selectNode(node)}
                        className={'block w-full text-left rounded-lg p-3 border transition-colors ' +
                          (active?.node_id === node.node_id
                            ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-300'
                            : 'border-slate-200 bg-white hover:border-indigo-300')}>
                        <span className="block text-sm font-medium leading-6">{node.title}</span>
                        <span className="mt-1 block text-xs text-slate-500">
                          {node.source_status === 'anchored' ? 'Source-linked' : 'No anchored source'} ·
                          {node.review_status === 'candidate' ? ' Not reviewed' : ' ' + node.review_status}
                        </span>
                      </button>
                    )}
                  </div>
                </div>
              })}
            </div>
            <p className="mt-4 text-xs text-slate-500">
              Map and outline share one source-backed data model. Clicking a claim changes the evidence panel.
            </p>
          </section>
          <aside className="lg:col-span-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
            aria-label="Evidence inspector">
            <h2 className="font-semibold mb-3">Inspect a claim</h2>
            {active ? <>
              <p className="font-semibold text-lg leading-7">{active.title}</p>
              <p className="my-3 text-sm rounded-lg bg-slate-100 p-3 text-slate-700">
                Source location confirmed · Scientific support <strong>not yet reviewed</strong>.
                A correctly located quote does not prove that a conclusion is true.
              </p>
              <div className="space-y-3">
                {activeRefs.length ? activeRefs.map(ref =>
                  <SourceQuote key={ref.evidence_id} reference={ref} bundle={bundle}/>
                ) : <p className="text-sm text-amber-800">No source reference is available.</p>}
              </div>
              <a className="mt-4 inline-block text-sm font-semibold text-indigo-700 underline"
                href={bundle.source_pdf_url + '#page=' + ((activeRefs[0]?.page_index ?? 0) + 1)}
                target="_blank" rel="noreferrer">
                Open cited PDF page
              </a>
              <p className="text-xs mt-3 text-slate-500">
                Text positions are exact Unicode offsets in the extracted source block.
                PDF glyph-accurate highlighting will be added in a later phase.
              </p>
            </> : <p className="text-slate-600">Select a claim on the research map.</p>}
          </aside>
        </div>
        <footer className="text-xs text-slate-500 py-3">
          Original teaching sample; no personal uploads, external model calls, real experiments or human-reviewed scientific claims.
          {bundle.rights}
        </footer>
      </>}
    </main>
  </div>
}
