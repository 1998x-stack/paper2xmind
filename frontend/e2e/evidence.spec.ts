import { test, expect } from '@playwright/test'

const paperId = 'a'.repeat(32)
const claimId = 'claim_' + 'b'.repeat(32)
const evidenceId = 'ev_' + 'c'.repeat(24)
const revisionId = 'd'.repeat(32)

const sourceBundle = {
  revision_id: revisionId,
  pdf_sha256: 'e'.repeat(64),
  state: 'PUBLISHED',
  bundle_hash: 'f'.repeat(64),
  review_outcome_sha256: null,
  review_outcome: null,
  documents: {
    document_ir: {
      blocks: [{
        block_id: 'blk_sample', page_index: 0,
        text: 'We report F1 score 0.76 on the evaluation dataset.',
      }],
    },
    claims: {
      claims: [{
        claim_id: claimId, kind: 'numeric_result',
        assertion: 'F1 score is 0.76',
        origin_type: 'author_result', support_status: 'candidate',
        evidence_ids: [evidenceId], assessment: null,
      }],
      evidence: [{
        evidence_id: evidenceId, block_id: 'blk_sample', page_index: 0,
        start_cp: 10, end_cp: 23, quote: 'F1 score 0.76',
      }],
    },
    review_analysis: {
      signals: [{
        claim_id: claimId, code: 'ORIGIN_PRIOR_WORK_RISK', severity: 'review',
      }],
      potential_conflicts: [],
    },
  },
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/papers', route => route.fulfill({
    json: { papers: [{ paper_id: paperId, title: 'Synthetic research paper',
                     status: 'READY', job_id: 'job_123' }] },
  }))
  await page.route('**/api/papers/*/chat', route => route.fulfill({
    json: { messages: [] },
  }))
  await page.route('**/api/papers/*/mindmap', route => route.fulfill({
    json: { paper_id: paperId, xmind_data: { id: 'root', title: 'Original tree', children: [] } },
  }))
})

test('inspect exact citation and submit authenticated human-review intent', async ({ page }) => {
  await page.route('**/api/evidence/papers/*/latest', route => {
    expect(route.request().headers()['authorization']).toBe('Bearer synthetic-review-token')
    return route.fulfill({ json: sourceBundle })
  })
  await page.route('**/api/evidence/papers/*/revisions/*/reviews', route => {
    const request = route.request()
    expect(request.method()).toBe('POST')
    expect(request.headers()['authorization']).toBe('Bearer synthetic-review-token')
    const body = request.postDataJSON()
    expect(body.claim_id).toBe(claimId)
    expect(body.verdict).toBe('supported')
    expect(body.expected_outcome_sha256).toBeNull()
    expect(body.nonce.length).toBeGreaterThanOrEqual(16)
    expect(body.rationale.length).toBeGreaterThanOrEqual(10)
    return route.fulfill({ json: {
      ...sourceBundle,
      review_outcome_sha256: '1'.repeat(64),
      review_outcome: { claims: [{
        ...sourceBundle.documents.claims.claims[0],
        support_status: 'supported',
        assessment: {
          method: 'human', evaluator_id: 'synthetic-reviewer',
          rationale: body.rationale,
        },
      }] },
    } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: /Synthetic research paper/ }).click()
  await page.getByRole('button', { name: 'Evidence inspector' }).click()
  await expect(page.getByRole('heading', { name: 'Evidence inspector' })).toBeVisible()
  await page.getByLabel('Evidence access token').fill('synthetic-review-token')
  await page.getByRole('button', { name: 'Load evidence' }).click()
  await expect(page.getByRole('heading', { name: 'F1 score is 0.76' })).toBeVisible()
  await expect(page.getByText('F1 score 0.76', { exact: true })).toBeVisible()
  await expect(page.getByText(/ORIGIN_PRIOR_WORK_RISK/)).toBeVisible()
  await page.getByLabel('Review decision').selectOption('supported')
  await page.getByLabel('Reasoning and checked context').fill(
    'The exact original sentence and experimental context were independently checked.'
  )
  await page.getByRole('button', { name: 'Record signed review' }).click()
  await expect(page.getByRole('status')).toContainText('Review saved')
  await expect(page.getByText('Reviewer: synthetic-reviewer')).toBeVisible()
})

test('access denial is visible; source is never rendered on a rejected request', async ({ page }) => {
  await page.route('**/api/evidence/papers/*/latest', route => route.fulfill({
    status: 401, json: { detail: 'Unauthorized' },
  }))
  await page.goto('/')
  await page.getByRole('button', { name: /Synthetic research paper/ }).click()
  await page.getByRole('button', { name: 'Evidence inspector' }).click()
  await page.getByLabel('Evidence access token').fill('wrong-token-in-test')
  await page.getByRole('button', { name: 'Load evidence' }).click()
  await expect(page.getByText('Evidence access failed (401).')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'F1 score is 0.76' })).toHaveCount(0)
})
