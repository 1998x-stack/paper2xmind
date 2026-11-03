import { test, expect } from '@playwright/test'

const quote = 'Baseline F1 0.72 and variant F1 0.76'
const text = 'Result: ' + quote + ' (illustrative only).'
const evidenceId = 'ev_original_01'

const demo = {
  demo_id: 'synthetic-retrieval',
  title: 'Fictional retrieval experiment (interactive sample)',
  source_kind: 'original_synthetic_pdf',
  rights: 'Original fictional teaching example.',
  disclaimer: 'This is a synthetic interactive product demonstration, NOT a published scientific experiment.',
  pdf_sha256: 'e'.repeat(64),
  source_pdf_url: '/api/public/demos/synthetic-retrieval/source.pdf',
  source_blocks: [{
    block_id: 'blk_source_1', page_index: 0,
    normalized_text: text,
  }],
  research_map: {
    root_id: 'paper_demo',
    revision_id: 'd'.repeat(32),
    contains_unreviewed_claims: true,
    nodes: [
      { node_id: 'paper_demo', parent_id: null, kind: 'paper',
        title: 'Research paper', claim_id: null, evidence_ids: [],
        source_status: 'unanchored', review_status: 'unverified', core_claim: false },
      { node_id: 'group_findings', parent_id: 'paper_demo', kind: 'group',
        title: 'Findings and experiments', claim_id: null, evidence_ids: [],
        source_status: 'unanchored', review_status: 'unverified', core_claim: false },
      { node_id: 'node_finding', parent_id: 'group_findings', kind: 'finding',
        title: 'The fictional variant has F1 0.76 versus baseline 0.72.',
        claim_id: 'claim_test', evidence_ids: [evidenceId],
        source_status: 'anchored', review_status: 'candidate', core_claim: true },
    ],
    evidence: [{
      evidence_id: evidenceId,
      block_id: 'blk_source_1', page_index: 0,
      start_cp: text.indexOf(quote),
      end_cp: text.indexOf(quote) + quote.length,
      quote,
    }],
  },
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/public/demos/synthetic-retrieval', route => {
    expect(route.request().headers()['authorization']).toBeUndefined()
    return route.fulfill({ json: demo })
  })
  await page.route('**/api/public/demos/synthetic-retrieval/source.pdf', route =>
    route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.4\n%mock browser only' })
  )
})

test('anonymous demo shows map, original quotation and outline', async ({ page }) => {
  await page.goto('/demo')
  await expect(page.getByRole('heading', { name: 'See the research. Inspect the evidence.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Research map' })).toBeVisible()
  await expect(page.getByText(quote, { exact: true })).toBeVisible()
  await expect(page.getByText(/Scientific support/)).toContainText('not yet reviewed')
  await expect(page.getByText(/Original synthetic example/)).toBeVisible()
  const finding = page.getByRole('button', { name: /fictional variant has F1/ })
  await expect(finding).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Outline' }).click()
  await expect(finding).toBeVisible()
  await expect(page.getByRole('button', { name: 'Outline' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('link', { name: 'Open PDF' })).toHaveAttribute('href', demo.source_pdf_url)
})

test('public demo API failure is visible, without false research map', async ({ page }) => {
  await page.unroute('**/api/public/demos/synthetic-retrieval')
  await page.route('**/api/public/demos/synthetic-retrieval', route =>
    route.fulfill({ status: 503, json: { detail: 'Unavailable' } })
  )
  await page.goto('/demo')
  await expect(page.getByRole('alert')).toContainText('public sample is unavailable')
  await expect(page.getByRole('heading', { name: 'Research map' })).toHaveCount(0)
})
