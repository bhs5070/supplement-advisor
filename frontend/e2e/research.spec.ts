import { expect, test, type Page } from '@playwright/test';

const id = '11111111-2222-4333-8444-555555555555';
const token = 'fixture-token';

function collectionReport() {
  return {
    scope: 'collection_only', summary: '제품 표시를 수집했습니다.',
    product: { name: '테스트 제품', manufacturer: '가온헬스', report_number: '2026012345' },
    claims: ['하루 한 번'], ingredients: [{ name: '비타민C', amount: '500', unit: 'mg', basis: '1일 기준' }],
    sources: [
      { id: 'product', url: 'https://example.org/product', title: '제품 페이지', kind: 'advertising', retrieved_at: '2026-11-11T00:00:00Z', excerpt: '제품 표시' },
      { id: 'official', url: 'https://foodsafetykorea.go.kr', title: '공식 등록 정보', kind: 'official', retrieved_at: '2026-11-11T00:00:00Z', excerpt: '신고번호 2026012345' },
    ],
    checks: [], limitations: ['제품 전체 효능은 판정하지 않았습니다.'], score: null, verdict: 'hold',
    official_match: {
      state: 'matched', reason: '공식 자료에서 제품 등록 정보를 대조했습니다.', reasons: [], evidence: [], candidates: [], queries: [],
      matched_record: { PRDLST_NM: '테스트 제품', BSSH_NM: '가온헬스', PRDLST_REPORT_NO: '2026012345' },
    },
  };
}

function legacyCollectionReport() {
  const report = collectionReport();
  const { report_number: _removedReportNumber, ...product } = report.product;
  return { ...report, product };
}

function researchReport(baseCollection: unknown = collectionReport()) {
  const roles = [
    ['composition', '성분·함량 표시'], ['claims', '기능성·광고 근거'],
    ['personal_fit', '개인 적합성'], ['safety', '안전성'], ['official_quality', '공식 정보·품질'],
  ].map(([role, question]) => ({
    role, question, status: role === 'personal_fit' ? 'not_applicable' : 'insufficient_evidence',
    findings: role === 'claims' ? [{ statement: '원료 연구는 제품 효과를 직접 입증하지 않습니다.', status: 'not_assessable', source_ids: ['paper-1'], quotes: [{ source_id: 'paper-1', excerpt: '원료 연구의 초록 일부' }], applicability: 'ingredient_only' }] : [],
    missing_information: [], reasons: role === 'claims' ? ['범위가 제한됨'] : role === 'composition' || role === 'safety' || role === 'official_quality' ? ['not_selected_by_supervisor'] : ['회원 프로필이 없어 평가하지 않았습니다.'],
  }));
  return {
    ...collectionReport(), scope: 'evidence_review', collection_report: baseCollection, score: null, verdict: 'hold',
    research: {
      status: 'partial', roles,
      sources: [
        { id: 'paper-1', kind: 'research', title: '원료 연구', url: 'https://pubmed.ncbi.nlm.nih.gov/123/', retrieved_at: '2026-11-11T00:00:00Z', provider: 'pubmed', access_scope: 'abstract', excerpt: '원료 연구의 초록 일부', doi: null, pmid: '123' },
        { id: 'unsafe-source', kind: 'research', title: '안전하지 않은 주소', url: 'javascript:alert(1)', retrieved_at: 'invalid', provider: 'test', access_scope: 'discovery', excerpt: '' },
      ],
      limitations: ['제품 전체 효능이나 개인 적합성을 판정하지 않았습니다.'], termination_reason: 'budget_exhausted',
      decisions: [
        { role: 'supervisor', action: 'dispatch', reason: '기능성 문구의 근거를 먼저 조사했습니다.' },
        { role: 'claims', action: 'search_literature', reason: '기능성 문구의 근거를 조회했습니다.' },
      ],
      usage: { total: 3, by_role: { supervisor: 1, claims: 2 } },
    },
  };
}

function payload(status: string, report: unknown, extra: Record<string, unknown> = {}) {
  return { id, status, product_name: '테스트 제품', report, error_code: null, message: null,
    missing_fields: [], can_supplement: false, supplemental_input_used: false,
    created_at: '2026-11-11T00:00:00Z', updated_at: '2026-11-11T00:00:00Z', ...extra };
}

async function setup(page: Page, report: unknown, status = 'completed', extra: Record<string, unknown> = {}) {
  const posts: unknown[] = [];
  await page.route('**/api/capabilities', (route) => route.fulfill({ json: { openai: 'not_configured', food_safety: 'not_configured' } }));
  await page.route('**/api/analyses', async (route) => {
    if (route.request().method() === 'POST') {
      posts.push(route.request().postDataJSON());
      await route.fulfill({ status: 202, json: { id, access_token: token, status: 'queued' } });
    } else await route.continue();
  });
  await page.route(`**/api/analyses/${id}`, (route) => route.fulfill({ json: payload(status, report, extra) }));
  await page.goto('/');
  return posts;
}

async function submit(page: Page) {
  await page.getByLabel('제품 URL').fill('https://example.org/product');
  await page.getByRole('button', { name: /제품 정보 확인하기/ }).click();
}

test('default collection request omits mode and collection report renders', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-chromium');
  const posts = await setup(page, collectionReport());
  await submit(page);
  await expect(page.getByRole('heading', { name: '확인한 정보와 남은 질문' })).toBeVisible();
  expect(posts).toHaveLength(1);
  expect(posts[0]).toEqual({ url: 'https://example.org/product' });
});

test('explicit evidence review posts mode and presents honest partial evidence', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-chromium');
  const posts = await setup(page, researchReport());
  const choice = page.getByRole('checkbox', { name: /공식 자료·논문 근거도 조사하기/ });
  await expect(choice).toBeVisible();
  await expect(page.getByText('조사한 범위와 출처를 보여줍니다. 점수·구매 추천은 하지 않습니다.')).toBeVisible();
  await choice.check();
  await submit(page);
  expect(posts).toHaveLength(1);
  expect(posts[0]).toEqual({ url: 'https://example.org/product', mode: 'evidence_review' });
  await expect(page.getByRole('heading', { name: '근거 조사 결과' })).toBeVisible();
  await expect(page.getByRole('region', { name: '근거 조사 결과' })).toBeVisible();
  await expect(page.getByRole('status').first()).toContainText('근거 조사 일부 완료');
  await expect(page.getByText('근거 조사', { exact: true })).toBeVisible();
  await expect(page.getByText(/일부 공개 근거/)).toBeVisible();
  await expect(page.getByText('공개 페이지 수집 · 일부 근거 조회 · 출처·한계 표시')).toBeVisible();
  await expect(page.locator('footer')).toContainText('근거 조사가 일부 완료되었습니다.');
  await expect(page.getByText('일부 공개 근거만 확인했습니다')).toBeVisible();
  for (const role of ['성분·함량 표시', '기능성·광고 근거', '개인 적합성', '안전성', '공식 정보·품질']) {
    await expect(page.getByRole('heading', { name: role, exact: true })).toBeVisible();
  }
  await expect(page.getByText('비회원의 개인 적합성은 평가하지 않았습니다.')).toBeVisible();
  await expect(page.getByRole('heading', { name: '원료 연구' })).toBeVisible();
  await expect(page.getByText('제품에 적용되는 근거로 해석하지 않습니다.')).toBeVisible();
  await expect(page.getByText('점수 없음 · 구매 추천 없음')).toBeVisible();
  await expect(page.getByText('이번 조사 범위에 포함되지 않았습니다.', { exact: true })).toHaveCount(3);
  await expect(page.getByText('not_selected_by_supervisor', { exact: true })).toHaveCount(0);
  await expect(page.getByText('조사 범위 선택')).toBeVisible();
  await expect(page.getByText('수집·조사 요청 시도 3회 (예약 기준, M1 수집 포함)')).toBeVisible();
  const source = page.getByRole('link', { name: /원료 연구/ });
  await expect(source).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/123/');
  await expect(page.getByRole('link', { name: /안전하지 않은 주소/ })).toHaveCount(0);
  await page.screenshot({ path: './work/verification/m2a/research-desktop.png', fullPage: true });
});

test('reuses the collection report for product, ingredient, and official-match details', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-chromium');
  const posts = await setup(page, researchReport());
  await submit(page);
  await page.getByText('기초 수집 결과 자세히 보기', { exact: true }).click();
  for (const value of ['테스트 제품', '가온헬스', '2026012345', '비타민C', '500 mg']) {
    await expect(page.getByText(value, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText('대조된 공식 등록 자료')).toBeVisible();
  await expect(page.getByText('공식 등록 정보')).toBeVisible();
  expect(posts).toHaveLength(1);
});

test('accepts an older complete collection report without report number', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-chromium');
  await setup(page, researchReport(legacyCollectionReport()));
  await submit(page);
  await expect(page.getByText('기초 수집 결과 자세히 보기', { exact: true })).toBeVisible();
  await page.getByText('기초 수집 결과 자세히 보기', { exact: true }).click();
  for (const value of ['테스트 제품', '가온헬스', '미확인', '비타민C', '500 mg']) {
    await expect(page.getByText(value, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText('기초 수집 결과가 없습니다')).toHaveCount(0);
});

test('falls back safely for an incomplete collection report', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-chromium');
  const report = researchReport();
  report.collection_report = { scope: 'collection_only', summary: '불완전한 보고서', product: { name: '테스트 제품' } };
  await setup(page, report);
  await submit(page);
  await expect(page.getByText(/기초 수집 결과가 없습니다/)).toBeVisible();
  await expect(page.getByText('불완전한 보고서', { exact: true })).toHaveCount(0);
});

test('shows completed and unavailable research states without changing collection labels', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-chromium');
  for (const [researchStatus, expected, scope] of [
    ['completed', '근거 조사 완료', '공개 페이지 수집 · 공개 근거 조사 · 출처·한계 표시'],
    ['unavailable', '근거 자료 조회 불가', '공개 페이지 수집 · 근거 자료 조회 불가'],
  ] as const) {
    const report = researchReport();
    report.research.status = researchStatus;
    await setup(page, report);
    await submit(page);
    await expect(page.getByRole('status').first()).toContainText(expected);
    await expect(page.getByText('근거 조사', { exact: true })).toBeVisible();
    await expect(page.getByText(scope)).toBeVisible();
    await page.getByRole('button', { name: '화면에서 지우기' }).click();
  }
  await setup(page, collectionReport());
  await submit(page);
  await expect(page.getByRole('status').first()).toContainText('수집 보고서 준비됨');
  await expect(page.getByText('M1 · 수집·식별', { exact: true })).toBeVisible();
  await expect(page.getByText('이 단계는 제품 정보의 수집·식별 보고서입니다.', { exact: false })).toBeVisible();
});

test('needs_input cannot be supplemented and damaged collection report does not crash', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-chromium');
  const posts = await setup(page, null, 'needs_input', { can_supplement: false, missing_fields: ['manufacturer'] });
  await submit(page);
  await expect(page.getByText(/기초 수집 결과가 없습니다/)).toBeVisible();
  await expect(page.getByRole('button', { name: /추가 정보 제출하기/ })).toHaveCount(0);
  expect(posts).toHaveLength(1);
});

test('terminal partial report does not re-post automatically', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-chromium');
  const posts = await setup(page, researchReport());
  await submit(page);
  await expect(page.getByRole('heading', { name: '근거 조사 결과' })).toBeVisible();
  await page.waitForTimeout(2_500);
  expect(posts).toHaveLength(1);
});

test('research report fits 375px mobile viewport', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile-chromium');
  await setup(page, researchReport());
  await submit(page);
  await expect(page.getByRole('heading', { name: '근거 조사 결과' })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
  await page.screenshot({ path: './work/verification/m2a/research-mobile.png', fullPage: true });
  await page.addStyleTag({ content: 'html { font-size: 125% !important; }' });
  const enlarged = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(enlarged.width).toBeLessThanOrEqual(enlarged.viewport);
  await page.setViewportSize({ width: 812, height: 375 });
  const landscape = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(landscape.width).toBeLessThanOrEqual(landscape.viewport);
});
