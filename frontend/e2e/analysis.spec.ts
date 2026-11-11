import { expect, test, type Page, type Route } from '@playwright/test';

const id = '11111111-2222-4333-8444-555555555555';
const token = 'browser-only-secret-token';

function result(status: string, extra: Record<string, unknown> = {}) {
  return {
    id, status, product_name: '테스트 제품', report: null, error_code: null,
    message: null, missing_fields: [], can_supplement: false, supplemental_input_used: false,
    created_at: '2026-11-09T00:00:00Z',
    updated_at: '2026-11-09T00:00:00Z', ...extra,
  };
}

function report() {
  return {
    scope: 'collection_only', summary: '<img src=x onerror="window.xss=1"> 확인 요약',
    product: { name: '테스트 제품', manufacturer: null, report_number: null },
    claims: ['<script>window.xss=2</script>'], ingredients: [],
    sources: [
      { id: 'unsafe', url: 'javascript:alert(1)', title: '악성 링크', kind: 'advertising', retrieved_at: '2026-11-09T00:00:00Z', excerpt: '' },
      { id: 'safe', url: 'https://example.org/product', title: '<svg onload=alert(1)>출처', kind: 'advertising', retrieved_at: '2026-11-09T00:00:00Z', excerpt: '<b>원문</b>' },
    ],
    checks: [], limitations: ['효과와 개인 적합성은 미평가'], score: null, verdict: 'hold',
  };
}

function normalReport() {
  return {
    scope: 'collection_only', summary: '공개 페이지에서 제품 표시 정보를 수집했습니다.',
    product: { name: '비타민C 데일리', manufacturer: '가온헬스', report_number: '2026012345' },
    claims: ['하루 한 번 섭취'],
    ingredients: [
      { name: '비타민C', amount: '500', unit: 'mg', basis: '1정 기준' },
      { name: '비타민D', amount: '10', unit: 'μg', basis: '1정 기준' },
      { name: '아연', amount: null, unit: null, basis: null },
    ],
    sources: [{ id: 'product-page', url: 'https://example.org/product', title: '제품 표시 정보', kind: 'advertising', retrieved_at: '2026-11-09T00:00:00Z', excerpt: '1일 1회, 1정' }],
    checks: [
      { name: '페이지 수집', status: 'verified', detail: '공개 페이지 응답을 확인했습니다.', source_ids: ['product-page'] },
      { name: '공식 등록 대조', status: 'unverified', detail: '등록 정보와의 동일성은 확인하지 못했습니다.', source_ids: [] },
      { name: '표시 정보 추출', status: 'unavailable', detail: '자동 추출 기능을 사용할 수 없습니다.', source_ids: [] },
      { name: '개인 적합성', status: 'not_applicable', detail: '비회원 개인 적합성은 미평가입니다.', source_ids: [] },
    ],
    limitations: ['효과와 개인 적합성은 미평가'], score: null, verdict: 'hold',
  };
}

function supplementableResult() {
  const base = normalReport();
  return result('needs_input', {
    report: {
      ...base,
      product: { name: '비타민C 데일리', manufacturer: null, report_number: null },
      missing_fields: ['manufacturer', 'report_number', 'ingredient_label'],
    },
    missing_fields: ['manufacturer', 'report_number', 'ingredient_label'],
    can_supplement: true,
    supplemental_input_used: false,
  });
}

function supplementedResult(status: string, extra: Record<string, unknown> = {}) {
  const base = normalReport();
  const supplemental = {
    ...base,
    product: {
      name: '비타민C 데일리', manufacturer: '가온헬스', report_number: '00102003004',
      field_sources: { name: 'user-input', manufacturer: 'user-input', report_number: 'user-input' },
    },
    ingredients: [
      { name: '비타민C', amount: '0005.00', unit: 'mg', basis: '1일 1정', source_id: 'user-input' },
      { name: '비타민D', amount: '10', unit: 'μg', basis: '1일 1정', source_id: 'user-input' },
      { name: '아연', amount: null, unit: null, basis: null, source_id: 'user-input' },
    ],
    sources: [
      ...base.sources,
      { id: 'user-input', url: '', title: '사용자 추가 입력', kind: 'user_input', retrieved_at: '2026-11-09T00:00:00Z', excerpt: '사용자 제공: 신고번호=00102003004' },
    ],
    missing_fields: [],
    score: null,
    verdict: 'hold',
  };
  return result(status, {
    report: status === 'completed' ? supplemental : null,
    missing_fields: [],
    can_supplement: false,
    supplemental_input_used: true,
    ...extra,
  });
}

async function mockCapabilities(page: Page) {
  await page.route('**/api/capabilities', (route) => route.fulfill({ json: { openai: 'not_configured', food_safety: 'not_configured' } }));
}

async function accept(page: Page) {
  await page.route('**/api/analyses', async (route) => {
    if (route.request().method() === 'POST') await route.fulfill({ json: { id, access_token: token, status: 'queued' }, status: 202 });
    else await route.continue();
  });
}

async function submitProduct(page: Page) {
  await page.getByLabel('제품 URL').fill('https://example.org/product');
  await page.getByRole('button', { name: /제품 정보 확인하기/ }).click();
}

for (const [status, label] of [
  ['queued', '수집 대기 중'], ['running', '제품 정보 확인 중'],
  ['needs_input', '추가 정보 확인 필요'], ['completed', '수집 보고서 준비됨'],
  ['failed', '수집을 마치지 못했어요'],
] as const) {
  test(`accepts analysis and renders ${status}`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop-chromium');
    await mockCapabilities(page);
    await accept(page);
    const headersSeen: string[] = [];
    const urlsSeen: string[] = [];
    await page.route(`**/api/analyses/${id}`, async (route: Route) => {
      headersSeen.push(route.request().headers()['x-analysis-token'] || '');
      urlsSeen.push(route.request().url());
      await route.fulfill({ json: result(status, status === 'completed' || status === 'needs_input' ? { report: report(), missing_fields: ['manufacturer'] } : {}) });
    });
    await page.goto('/');
    await expect(page.getByRole('heading', { name: '구매 전, 근거부터.' })).toBeVisible();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: '본문 바로가기' })).toBeFocused();
    await submitProduct(page);
    await expect(page.getByRole('status').first()).toContainText(label, { timeout: 8_000 });
    expect(headersSeen.length).toBeGreaterThan(0);
    expect(headersSeen.every((value) => value === token)).toBeTruthy();
    expect(urlsSeen.every((value) => !value.includes(token))).toBeTruthy();
    if (status === 'completed' || status === 'needs_input') {
      await expect(page.getByText('<img src=x onerror="window.xss=1"> 확인 요약')).toBeVisible();
      await expect(page.getByText('<script>window.xss=2</script>')).toBeVisible();
      await expect(page.getByRole('link', { name: /악성 링크/ })).toHaveCount(0);
      const safe = page.getByRole('link', { name: /출처/ });
      await expect(safe).toHaveAttribute('href', 'https://example.org/product');
      await expect(safe).toHaveAttribute('rel', 'noopener noreferrer');
      expect(await page.evaluate(() => (window as Window & { xss?: number }).xss)).toBeUndefined();
    }
    if (status === 'completed') await page.screenshot({ path: './work/verification/security-desktop-report.png', fullPage: true });
  });
}

test('shows 404 for an invalid token', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium');
  await mockCapabilities(page);
  await page.addInitScript(() => sessionStorage.setItem('supplement-advisor.current-analysis', JSON.stringify({ id: '11111111-2222-4333-8444-555555555555', access_token: 'deliberately-invalid-token' })));
  const observedTokens: string[] = [];
  await page.route(`**/api/analyses/${id}`, (route) => {
    const observedToken = route.request().headers()['x-analysis-token'] || '';
    observedTokens.push(observedToken);
    if (observedToken !== token) return route.fulfill({ status: 404, json: { detail: 'Not found' } });
    return route.fulfill({ json: result('completed', { report: normalReport() }) });
  });
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('결과를 찾을 수 없거나');
  expect(observedTokens.length).toBeGreaterThan(0);
  expect(observedTokens.every((value) => value === 'deliberately-invalid-token')).toBeTruthy();
});

test('polls queued to running to completed and restores a valid session after reload', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium');
  await mockCapabilities(page);
  await accept(page);
  const observedTokens: string[] = [];
  let read = 0;
  await page.route(`**/api/analyses/${id}`, async (route) => {
    observedTokens.push(route.request().headers()['x-analysis-token'] || '');
    const stage = read++;
    if (stage === 0) return route.fulfill({ json: result('queued') });
    if (stage === 1) return route.fulfill({ json: result('running') });
    return route.fulfill({ json: result('completed', { report: normalReport() }) });
  });
  await page.goto('/');
  await submitProduct(page);
  await expect(page.getByRole('status').first()).toContainText('수집 대기 중');
  await expect(page.getByRole('status').first()).toContainText('제품 정보 확인 중', { timeout: 5_000 });
  await expect(page.getByRole('heading', { name: '확인한 정보와 남은 질문' })).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText('500 mg')).toBeVisible();
  await expect(page.getByText('10 μg')).toBeVisible();
  await expect(page.getByRole('row', { name: /아연 함량 미확인 미확인/ })).toBeVisible();
  for (const label of ['확인됨', '미확인', '확인 불가', '미평가']) {
    await expect(page.locator('.badge').filter({ hasText: label })).toBeVisible();
  }
  await page.reload();
  await expect(page.getByRole('heading', { name: '확인한 정보와 남은 질문' })).toBeVisible();
  expect(observedTokens.length).toBeGreaterThanOrEqual(4);
  expect(observedTokens.every((value) => value === token)).toBeTruthy();
  await expect(page.getByText('500 mg')).toBeVisible();
  await page.screenshot({ path: './work/verification/normal-desktop-report.png', fullPage: true });
});

test('captures a normal mobile report without horizontal overflow', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium');
  await mockCapabilities(page);
  await accept(page);
  await page.route(`**/api/analyses/${id}`, (route) => route.fulfill({ json: result('completed', { report: normalReport() }) }));
  await page.goto('/');
  await expect(page.getByLabel('제품 URL')).toBeVisible();
  await submitProduct(page);
  await expect(page.getByRole('heading', { name: '확인한 정보와 남은 질문' })).toBeVisible();
  await expect(page.getByText('500 mg')).toBeVisible();
  await expect(page.getByText('10 μg')).toBeVisible();
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
  await page.screenshot({ path: './work/verification/normal-mobile-report.png', fullPage: true });
});

test('separates an official candidate from a confirmed registration and shows field evidence', async ({ page }, testInfo) => {
  await mockCapabilities(page);
  await accept(page);
  const base = normalReport();
  const candidateReport = {
    ...base,
    product: { name: '비타민C 데일리 60정', manufacturer: '가온헬스', report_number: null },
    sources: [...base.sources, {
      id: 'official-i0030', url: 'https://foodsafetykorea.go.kr', title: '식품안전나라 I0030 품목제조 신고사항',
      kind: 'official', retrieved_at: '2026-11-09T01:00:00Z', excerpt: '비타민C 데일리 / 가온헬스',
    }],
    official_match: {
      state: 'candidate', reason: '후보가 있으나 동일 제품을 확정할 근거가 부족합니다.',
      reasons: ['신고번호가 페이지에서 확인되지 않았습니다.'],
      evidence: [
        { field: 'PRDLST_NM', page_value: '비타민C 데일리 60정', official_value: '비타민C 데일리', outcome: 'match', source_ids: ['product-page', 'official-i0030'] },
        { field: 'PRDLST_REPORT_NO', page_value: null, official_value: '202699991', outcome: 'missing', source_ids: ['official-i0030'] },
      ],
      candidates: [{ source_id: 'official-i0030', record: { PRDLST_NM: '비타민C 데일리', BSSH_NM: '가온헬스', PRDLST_REPORT_NO: '202699991', LAST_UPDT_DTM: '2026-10-18' } }],
      queries: [{ field: 'PRDLST_NM', value: '비타민C 데일리', total_count: 1, returned_count: 1, truncated: false }],
      matched_record: null,
    },
  };
  let currentReport: Record<string, unknown> = candidateReport;
  await page.route(`**/api/analyses/${id}`, (route) => route.fulfill({ json: result('completed', { report: currentReport }) }));
  await page.goto('/');
  await submitProduct(page);
  await expect(page.getByRole('heading', { name: '확인한 정보와 남은 질문' })).toBeVisible();
  await expect(page.getByText('공식 후보 있음 · 추가 확인 필요')).toBeVisible();
  await expect(page.getByText(/구매 추천이나 제품 품질 판정이 아닙니다/)).toBeVisible();
  await expect(page.getByText('모순', { exact: true })).toHaveCount(0);
  await expect(page.locator('.evidence-outcome.missing')).toHaveText('누락');
  await expect(page.getByRole('rowheader', { name: '공식 신고번호' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '202699991', exact: true })).toBeVisible();
  await expect(page.locator('.product-fields')).not.toContainText('202699991');
  if (testInfo.project.name === 'mobile-chromium') {
    const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
    expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
  }
  await page.screenshot({ path: `./work/verification/official-candidate-${testInfo.project.name.replace('-chromium', '')}.png`, fullPage: true });
  await page.getByText('공식 검색 범위 1건 보기').click();
  await expect(page.getByText(/전체 1건/)).toBeVisible();
  await expect(page.getByText('자료 버전·변경일:')).toHaveCount(0);

  const matchedReport = {
    ...candidateReport,
    checks: base.checks.map((check) => check.name === '공식 등록 대조' ? { ...check, status: 'verified', detail: '제품명·제조사와 추가 성분 근거를 대조했습니다.', source_ids: ['product-page', 'official-i0030'] } : check),
    official_match: {
      ...candidateReport.official_match,
      state: 'matched', reason: '제품명·제조사와 페이지의 추가 성분 근거가 공식 자료와 일치합니다.', reasons: [],
      evidence: [
        { field: 'product_name', page_value: '비타민C 데일리 60정', official_value: '비타민C 데일리 60정', outcome: 'match', source_ids: ['product-page', 'official-i0030'] },
        { field: 'manufacturer', page_value: '가온헬스', official_value: '가온헬스', outcome: 'match', source_ids: ['product-page', 'official-i0030'] },
        { field: 'ingredient_amount', page_value: '비타민C 500 mg', official_value: '비타민C 500 mg', outcome: 'match', source_ids: ['product-page', 'official-i0030'] },
      ],
      candidates: [],
      matched_record: { PRDLST_NM: '비타민C 데일리 60정', BSSH_NM: '가온헬스', PRDLST_REPORT_NO: '202699991', LAST_UPDT_DTM: '2026-10-18' },
    },
    sources: candidateReport.sources.map((source: { id: string }) => source.id === 'official-i0030'
      ? { ...source, document_id: '202699991', version: '2026-10-18' }
      : source),
  };
  currentReport = matchedReport;
  await page.reload();
  await expect(page.getByText('공식 등록 확인')).toBeVisible();
  await expect(page.getByText('제품명·제조사와 페이지의 추가 성분 근거가 공식 자료와 일치합니다.')).toBeVisible();
  await expect(page.locator('.evidence-outcome.missing')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '대조된 공식 등록 자료' })).toBeVisible();
  await expect(page.locator('.product-fields')).not.toContainText('202699991');
  await expect(page.getByText('공식 신고번호:')).toBeVisible();
  await expect(page.getByText('자료 버전·변경일: 2026-10-18')).toBeVisible();
  await page.screenshot({ path: `./work/verification/official-matched-${testInfo.project.name.replace('-chromium', '')}.png`, fullPage: true });

  const nameDifferenceReport = {
    ...matchedReport,
    product: { name: 'ERr731® 여성 갱년기영양제', manufacturer: '(주)서흥', report_number: '200400200062002' },
    ingredients: [
      { name: '비타민D', amount: null, unit: null, basis: null },
      { name: '비타민K', amount: null, unit: null, basis: null },
      { name: '루바브뿌리추출물(ERr731®)', amount: null, unit: null, basis: null },
    ],
    missing_fields: ['ingredient_amount_basis', 'formulation'],
    sources: matchedReport.sources.map((source: { id: string }) => source.id === 'official-i0030'
      ? { ...source, excerpt: '이알하나 ERr731 / (주)서흥 / 200400200062002', document_id: '200400200062002', version: '20251215' }
      : { ...source, title: 'ER Hana 제품 페이지', excerpt: 'ERr731® 여성 갱년기영양제 / (주)서흥 / 200400200062002' }),
    checks: base.checks.map((check) => check.name === '공식 등록 대조' ? { ...check, status: 'verified', detail: '공식 등록정보 대조 확인 — 판매명 차이 있음. 주요 원료는 대조했으며 함량 기준과 제형은 미확인입니다.', source_ids: ['product-page', 'official-i0030'] } : check),
    official_match: {
      ...matchedReport.official_match,
      reason: '신고번호·제조사·주요 기능성 원료를 대조했습니다. 함량 기준과 제형은 비교 자료가 부족합니다.',
      reasons: ['registration_identity_with_name_difference'],
      name_difference: { page_name: 'ERr731® 여성 갱년기영양제', official_name: '이알하나 ERr731' },
      evidence: [
        { field: 'PRDLST_NM', page_value: 'ERr731® 여성 갱년기영양제', official_value: '이알하나 ERr731', outcome: 'conflict', source_ids: ['product-page', 'official-i0030'] },
        { field: 'BSSH_NM', page_value: '(주)서흥', official_value: '(주)서흥', outcome: 'match', source_ids: ['product-page', 'official-i0030'] },
        { field: 'PRDLST_REPORT_NO', page_value: '200400200062002', official_value: '200400200062002', outcome: 'match', source_ids: ['product-page', 'official-i0030'] },
        { field: 'RAWMTRL_NM', page_value: '비타민D, 비타민K, 루바브뿌리추출물(ERr731®)', official_value: '비타민 D, 비타민 K, 루바브뿌리추출물(ERr731Ⓡ)', outcome: 'match', source_ids: ['product-page', 'official-i0030'] },
        { field: 'ingredient_amount_basis', page_value: null, official_value: '비타민D 10 ㎍/0.08g · 비타민K 70 ㎍/0.08g', outcome: 'missing', source_ids: ['official-i0030'] },
        { field: 'dosage_form', page_value: null, official_value: '정', outcome: 'missing', source_ids: ['official-i0030'] },
      ],
      matched_record: {
        PRDLST_NM: '이알하나 ERr731', BSSH_NM: '(주)서흥', PRDLST_REPORT_NO: '200400200062002',
        RAWMTRL_NM: '비타민 D, 루바브뿌리추출물(ERr731Ⓡ)(제2024-17호), 비타민 K',
        STDR_STND: '비타민D 10 ㎍/0.08g · 비타민K 70 ㎍/0.08g', PRDT_SHAP_CD_NM: '정',
      },
    },
  };
  currentReport = nameDifferenceReport;
  await page.reload();
  await expect(page.getByRole('heading', { name: '공식 등록정보 대조 확인 — 판매명 차이 있음' })).toBeVisible();
  await expect(page.getByRole('status').getByText('공식 등록정보 대조 확인 — 판매명 차이 있음')).toBeVisible();
  await expect(page.getByLabel('판매명과 공식 등록명 차이').getByText('ERr731® 여성 갱년기영양제', { exact: true })).toBeVisible();
  await expect(page.getByLabel('판매명과 공식 등록명 차이').getByText('이알하나 ERr731', { exact: true })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: '공식 제품명' })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: '주요 기능성 원료' })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: '함량 및 기준' })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: '제형' })).toBeVisible();
  await expect(page.locator('.evidence-outcome.conflict')).toHaveText('모순');
  await expect(page.getByText('함량·섭취 기준은 비교 근거가 부족합니다. 제형은 페이지에서 확인되지 않았습니다.')).toBeVisible();
  await expect(page.getByText('비교', { exact: true })).toBeVisible();
  await expect(page.locator('.official-evidence .evidence-outcome.missing')).toHaveCount(2);
  await expect(page.locator('.product-fields')).toContainText('ERr731® 여성 갱년기영양제');
  await expect(page.locator('.product-fields')).toContainText('200400200062002');
  await page.screenshot({ path: `./work/verification/official-name-difference-${testInfo.project.name.replace('-chromium', '')}.png`, fullPage: true });
});

test('offers retry after a network failure and ignores a late response after reset', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium');
  await mockCapabilities(page);
  await accept(page);
  let reads = 0;
  let releaseLate: (() => void) | undefined;
  await page.route(`**/api/analyses/${id}`, async (route) => {
    reads += 1;
    if (reads === 1) return route.abort('failed');
    if (reads === 2) return route.fulfill({ json: result('running') });
    if (reads === 3) {
      await new Promise<void>((resolve) => { releaseLate = resolve; });
      return route.fulfill({ json: result('completed', { report: report() }) });
    }
    return route.fulfill({ json: result('completed', { report: report() }) });
  });
  await page.goto('/');
  await submitProduct(page);
  await expect(page.getByRole('alert')).toContainText('서버 연결이 끊겼거나');
  await page.getByRole('button', { name: '조회 다시 시도' }).click();
  await expect(page.getByRole('status').first()).toContainText('제품 정보 확인 중');
  await expect.poll(() => reads).toBe(3);
  await page.getByRole('button', { name: '화면에서 지우기' }).click();
  releaseLate?.();
  await page.waitForTimeout(300);
  await expect(page.getByRole('heading', { name: '하나의 보고서로, 차분하게' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '확인한 정보와 남은 질문' })).toHaveCount(0);
});

test('submits one optional supplement batch, preserves values, and renders user provenance', async ({ page }, testInfo) => {
  await mockCapabilities(page);
  await accept(page);
  let reads = 0;
  const supplementPosts: { token: string; body: Record<string, unknown> }[] = [];
  await page.route(`**/api/analyses/${id}`, async (route) => {
    const stage = reads++;
    if (stage === 0) return route.fulfill({ json: supplementableResult() });
    if (stage === 1) return route.fulfill({ json: result('queued', { supplemental_input_used: true }) });
    if (stage === 2) return route.fulfill({ json: result('running', { supplemental_input_used: true }) });
    return route.fulfill({ json: supplementedResult('completed') });
  });
  await page.route(`**/api/analyses/${id}/supplement`, async (route) => {
    supplementPosts.push({
      token: route.request().headers()['x-analysis-token'] || '',
      body: route.request().postDataJSON() as Record<string, unknown>,
    });
    await route.fulfill({ status: 202, json: { id, status: 'queued' } });
  });

  await page.goto('/');
  await submitProduct(page);
  await expect(page.getByRole('heading', { name: '알고 있는 정보를 한 번 보태 주세요' })).toBeVisible();
  await expect(page.getByText(/기존 성분 목록을 이번에 입력한 목록으로 바꿉니다/)).toBeVisible();
  await page.getByRole('button', { name: '추가 정보 제출하기' }).click();
  await expect(page.getByRole('alert')).toContainText('하나 이상을 입력해 주세요');
  expect(supplementPosts).toHaveLength(0);

  await page.locator('#supplement-product-name').fill('비타민C 데일리');
  await page.locator('#supplement-manufacturer').fill('가온헬스');
  await page.getByLabel('품목제조 신고번호').fill('00102003004');
  for (let index = 0; index < 4; index += 1) await page.getByRole('button', { name: '성분 추가' }).click();
  await page.getByLabel('성분 이름').nth(0).fill('비타민C');
  await page.getByLabel('표시 함량').nth(0).fill('0005.00');
  await page.getByLabel('성분 1 단위').selectOption('mg');
  await page.getByLabel('섭취 기준').nth(0).fill('1일 1정');
  await page.getByLabel('성분 이름').nth(1).fill('비타민D');
  await page.getByLabel('표시 함량').nth(1).fill('10');
  await page.getByLabel('성분 2 단위').selectOption('μg');
  await page.getByLabel('섭취 기준').nth(1).fill('1일 1정');
  await page.getByLabel('성분 이름').nth(2).fill('아연');
  if (testInfo.project.name === 'desktop-chromium') await page.screenshot({ path: './work/verification/supplement-desktop-form.png', fullPage: true });
  if (testInfo.project.name === 'mobile-chromium') await page.screenshot({ path: './work/verification/supplement-mobile-form.png', fullPage: true });

  await page.getByRole('button', { name: '추가 정보 제출하기' }).click();
  await expect.poll(() => supplementPosts.length).toBe(1);
  await expect(page.getByText('0005.00 mg')).toBeVisible({ timeout: 8_000 });
  expect(supplementPosts).toHaveLength(1);
  expect(supplementPosts[0].token).toBe(token);
  expect(supplementPosts[0].body).toMatchObject({
    product_name: '비타민C 데일리', manufacturer: '가온헬스', report_number: '00102003004',
    ingredients: [
      { name: '비타민C', amount: '0005.00', unit: 'mg', basis: '1일 1정' },
      { name: '비타민D', amount: '10', unit: 'μg', basis: '1일 1정' },
      { name: '아연', amount: null, unit: null, basis: null },
    ],
  });
  expect((supplementPosts[0].body.ingredients as unknown[])).toHaveLength(3);
  await expect(page.locator('.product-fields').getByText('00102003004')).toBeVisible();
  await expect(page.getByText('0005.00 mg')).toBeVisible();
  await expect(page.getByText('10 μg')).toBeVisible();
  await expect(page.getByRole('row', { name: /아연.*함량 미확인.*미확인/ })).toBeVisible();
  await expect(page.getByText('(사용자 추가 입력)').first()).toBeVisible();
  await expect(page.getByText('사용자 제공', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: '사용자 추가 입력' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '추가 정보 제출하기' })).toHaveCount(0);
  await page.reload();
  await expect(page.getByText('0005.00 mg')).toBeVisible();
  await expect(page.getByRole('button', { name: '추가 정보 제출하기' })).toHaveCount(0);
  if (testInfo.project.name === 'desktop-chromium') await page.screenshot({ path: './work/verification/supplement-desktop-report.png', fullPage: true });
  if (testInfo.project.name === 'mobile-chromium') await page.screenshot({ path: './work/verification/supplement-mobile-report.png', fullPage: true });
});

test('does not offer another supplement when a previous batch still needs information', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium');
  await mockCapabilities(page);
  await accept(page);
  await page.route(`**/api/analyses/${id}`, (route) => route.fulfill({ json: supplementedResult('needs_input', { report: { ...normalReport(), missing_fields: ['report_number'] }, missing_fields: ['report_number'], message: '추가 입력 후에도 일부 정보가 부족합니다.' }) }));
  await page.goto('/');
  await submitProduct(page);
  await expect(page.getByText(/추가 정보 입력을 한 번 사용했습니다/)).toBeVisible();
  await expect(page.getByRole('button', { name: '추가 정보 제출하기' })).toHaveCount(0);
  await expect(page.getByText('제품 점수 미산정')).toBeVisible();
});

test('reconciles a 409 instead of allowing a second supplement', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium');
  await mockCapabilities(page);
  await accept(page);
  let reads = 0;
  let posts = 0;
  await page.route(`**/api/analyses/${id}`, (route) => {
    if (reads++ === 0) return route.fulfill({ json: supplementableResult() });
    return route.fulfill({ json: supplementedResult('needs_input', { report: { ...normalReport(), missing_fields: ['report_number'] }, missing_fields: ['report_number'], message: '이번 추가 입력은 완료되었습니다.' }) });
  });
  await page.route(`**/api/analyses/${id}/supplement`, async (route) => {
    posts += 1;
    expect(route.request().headers()['x-analysis-token']).toBe(token);
    await route.fulfill({ status: 409, json: { detail: 'Additional input already received' } });
  });
  await page.goto('/');
  await submitProduct(page);
  await page.locator('#supplement-manufacturer').fill('가온헬스');
  await page.getByRole('button', { name: '추가 정보 제출하기' }).click();
  await expect(page.getByText(/추가 정보 입력을 한 번 사용했습니다/)).toBeVisible();
  await expect(page.getByRole('button', { name: '추가 정보 제출하기' })).toHaveCount(0);
  expect(posts).toBe(1);
});

test('hides the supplement form after a lost response until the status is reconciled', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium');
  await mockCapabilities(page);
  await accept(page);
  let reads = 0;
  let posts = 0;
  await page.route(`**/api/analyses/${id}`, (route) => {
    if (reads++ === 0) return route.fulfill({ json: supplementableResult() });
    return route.fulfill({ json: supplementedResult('queued') });
  });
  await page.route(`**/api/analyses/${id}/supplement`, (route) => {
    posts += 1;
    return route.abort('failed');
  });
  await page.goto('/');
  await submitProduct(page);
  await page.locator('#supplement-manufacturer').fill('가온헬스');
  await page.getByRole('button', { name: '추가 정보 제출하기' }).click();
  await expect(page.getByRole('status').first()).toContainText('수집 대기 중');
  await expect(page.getByRole('button', { name: '추가 정보 제출하기' })).toHaveCount(0);
  expect(posts).toBe(1);
});

test('hides supplement form on a 404 response from the supplement endpoint', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium');
  await mockCapabilities(page);
  await page.addInitScript(() => sessionStorage.setItem('supplement-advisor.current-analysis', JSON.stringify({ id: '11111111-2222-4333-8444-555555555555', access_token: 'wrong-supplement-token' })));
  const suppliedTokens: string[] = [];
  await page.route(`**/api/analyses/${id}`, (route) => route.fulfill({ json: supplementableResult() }));
  await page.route(`**/api/analyses/${id}/supplement`, (route) => {
    suppliedTokens.push(route.request().headers()['x-analysis-token'] || '');
    return route.fulfill({ status: 404, json: { detail: 'Not found' } });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '알고 있는 정보를 한 번 보태 주세요' })).toBeVisible();
  await page.locator('#supplement-manufacturer').fill('가온헬스');
  await page.getByRole('button', { name: '추가 정보 제출하기' }).click();
  await expect(page.getByRole('alert')).toContainText('결과를 찾을 수 없거나');
  expect(suppliedTokens).toEqual(['wrong-supplement-token']);
  await expect(page.getByRole('button', { name: '추가 정보 제출하기' })).toHaveCount(0);
});

