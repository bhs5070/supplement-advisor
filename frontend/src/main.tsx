import { StrictMode, useEffect, useRef, useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { Report } from './Report';
import { ResearchReport as ResearchReportView } from './ResearchReport';
import { evidenceStatusLabels, isHandle, isPending, missingLabel, statusLabels, type AnalysisHandle, type AnalysisResult } from './types';
import './style.css';

const STORAGE_KEY = 'supplement-advisor.current-analysis';

function restoreAnalysis(): AnalysisHandle | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    return isHandle(value) ? value : null;
  } catch {
    return null;
  }
}

type Capabilities = { openai: string; food_safety: string };
type IngredientDraft = { name: string; amount: string; unit: string; otherUnit: string; basis: string };

function emptyIngredient(): IngredientDraft {
  return { name: '', amount: '', unit: '', otherUnit: '', basis: '' };
}

function App() {
  const [url, setUrl] = useState('');
  const [productName, setProductName] = useState('');
  const [evidenceReview, setEvidenceReview] = useState(false);
  const [handle, setHandle] = useState<AnalysisHandle | null>(restoreAnalysis);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState(false);
  const [capabilityRetry, setCapabilityRetry] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [queryError, setQueryError] = useState('');
  const [storageWarning, setStorageWarning] = useState(false);
  const [queryRetry, setQueryRetry] = useState(0);
  const [supplementProductName, setSupplementProductName] = useState('');
  const [supplementManufacturer, setSupplementManufacturer] = useState('');
  const [supplementReportNumber, setSupplementReportNumber] = useState('');
  const [supplementIngredients, setSupplementIngredients] = useState<IngredientDraft[]>([]);
  const [supplementing, setSupplementing] = useState(false);
  const [supplementError, setSupplementError] = useState('');
  const [supplementUncertain, setSupplementUncertain] = useState(false);
  const submitController = useRef<AbortController | null>(null);
  const supplementController = useRef<AbortController | null>(null);
  const submission = useRef(0);

  useEffect(() => () => {
    submission.current += 1;
    submitController.current?.abort();
    supplementController.current?.abort();
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10_000);
    setCapabilityError(false);
    fetch('/api/capabilities', { signal: controller.signal, cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error('unavailable');
        const value = await response.json() as Capabilities;
        if (typeof value.openai !== 'string' || typeof value.food_safety !== 'string') throw new Error('invalid');
        if (active) setCapabilities(value);
      })
      .catch(() => { if (active) setCapabilityError(true); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [capabilityRetry]);

  useEffect(() => {
    if (!handle) { setPolling(false); return; }
    let active = true;
    let timer: number | undefined;
    let controller: AbortController | undefined;
    setQueryError('');
    setPolling(true);
    async function read() {
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller?.abort(), 15_000);
      try {
        const response = await fetch(`/api/analyses/${handle!.id}`, {
          headers: { 'X-Analysis-Token': handle!.access_token },
          signal: controller.signal,
          cache: 'no-store',
        });
        if (!response.ok) {
          throw new Error(response.status === 404
            ? '결과를 찾을 수 없거나 이 브라우저 세션에 조회 권한이 없습니다.'
            : '결과를 조회할 수 없습니다. 잠시 후 다시 시도해 주세요.');
        }
        const value = await response.json() as AnalysisResult;
        if (value.id !== handle!.id || !Object.hasOwn(statusLabels, value.status)) throw new Error('서버 응답을 확인할 수 없습니다.');
        if (!active) return;
        setResult(value);
        setSupplementUncertain(false);
        if (isPending(value.status)) timer = window.setTimeout(read, 2_000);
        else setPolling(false);
      } catch (error) {
        if (!active) return;
        setPolling(false);
        setQueryError(error instanceof Error && error.name !== 'AbortError' && error.message !== 'Failed to fetch'
          ? error.message : '서버 연결이 끊겼거나 응답이 지연되었습니다. 조회를 다시 시도해 주세요.');
      } finally {
        window.clearTimeout(timeout);
      }
    }
    void read();
    return () => { active = false; controller?.abort(); window.clearTimeout(timer); };
  }, [handle, queryRetry]);

  function persist(next: AnalysisHandle | null) {
    try {
      if (next) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      else sessionStorage.removeItem(STORAGE_KEY);
      setStorageWarning(false);
    } catch {
      setStorageWarning(true);
    }
  }

  function reset() {
    submission.current += 1;
    submitController.current?.abort();
    supplementController.current?.abort();
    setSubmitting(false);
    setSupplementing(false);
    setHandle(null);
    setResult(null);
    setQueryError('');
    setSubmitError('');
    setSupplementError('');
    setSupplementUncertain(false);
    setSupplementProductName('');
    setSupplementManufacturer('');
    setSupplementReportNumber('');
    setSupplementIngredients([]);
    persist(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = (() => { try { return new URL(url.trim()); } catch { return null; } })();
    if (!parsed || !['http:', 'https:'].includes(parsed.protocol)) {
      setSubmitError('http:// 또는 https://로 시작하는 제품 페이지 주소를 입력해 주세요.');
      return;
    }
    reset();
    const version = submission.current;
    const controller = new AbortController();
    submitController.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    setSubmitting(true);
    try {
      const response = await fetch('/api/analyses', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url.trim(),
          ...(productName.trim() ? { product_name: productName.trim() } : {}),
          ...(evidenceReview ? { mode: 'evidence_review' } : {}),
        }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(response.status === 422
        ? '주소 형식과 공개 접속 가능 여부를 확인해 주세요. 내부 주소와 제한된 포트는 사용할 수 없습니다.'
        : '조사를 접수할 수 없습니다. 잠시 후 다시 시도해 주세요.');
      const value: unknown = await response.json();
      if (!isHandle(value)) throw new Error('접수 응답을 확인할 수 없습니다.');
      if (submission.current !== version) return;
      const next = { id: value.id, access_token: value.access_token };
      persist(next);
      setHandle(next);
    } catch (error) {
      if (submission.current !== version) return;
      setSubmitError(error instanceof Error && error.name !== 'AbortError' && error.message !== 'Failed to fetch'
        ? error.message : '접수 응답을 받지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.');
    } finally {
      window.clearTimeout(timeout);
      if (submission.current === version) setSubmitting(false);
    }
  }

  async function submitSupplement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!handle || !result?.can_supplement || supplementController.current) return;
    const productNameValue = supplementProductName.trim();
    const manufacturerValue = supplementManufacturer.trim();
    const reportNumberValue = supplementReportNumber.trim();
    if (reportNumberValue && !/^[0-9]+$/.test(reportNumberValue)) {
      setSupplementError('품목제조 신고번호는 숫자만 입력해 주세요. 앞의 0도 그대로 유지됩니다.');
      return;
    }
    const ingredients = supplementIngredients
      .filter((item) => item.name.trim())
      .map((item) => ({
        name: item.name.trim(),
        amount: item.amount.trim() || null,
        unit: item.unit === '기타' ? item.otherUnit.trim() || null : item.unit || null,
        basis: item.basis.trim() || null,
      }));
    if (!productNameValue && !manufacturerValue && !reportNumberValue && ingredients.length === 0) {
      setSupplementError('제품명, 제조사, 신고번호 또는 성분 이름 중 하나 이상을 입력해 주세요.');
      return;
    }

    const payload = {
      ...(productNameValue ? { product_name: productNameValue } : {}),
      ...(manufacturerValue ? { manufacturer: manufacturerValue } : {}),
      ...(reportNumberValue ? { report_number: reportNumberValue } : {}),
      ingredients,
    };
    const version = submission.current;
    const controller = new AbortController();
    supplementController.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    setSupplementing(true);
    setSupplementError('');
    try {
      const response = await fetch(`/api/analyses/${handle.id}/supplement`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Analysis-Token': handle.access_token },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (submission.current !== version) return;
      if (response.status === 409) {
        setSupplementUncertain(true);
        setQueryRetry((value) => value + 1);
        return;
      }
      if (response.status === 404) {
        setSupplementUncertain(true);
        setQueryError('결과를 찾을 수 없거나 이 브라우저 세션에 조회 권한이 없습니다.');
        return;
      }
      if (response.status === 422) {
        setSupplementError('입력 내용을 확인해 주세요. 신고번호는 숫자로, 성분 이름은 비워 둘 수 없습니다.');
        return;
      }
      if (!response.ok) throw new Error('supplement_failed');
      const accepted: unknown = await response.json();
      if (!accepted || typeof accepted !== 'object' || (accepted as { id?: unknown }).id !== handle.id || (accepted as { status?: unknown }).status !== 'queued') {
        throw new Error('invalid_acceptance');
      }
      if (submission.current !== version) return;
      setSupplementUncertain(true);
      setResult((current) => current ? {
        ...current, status: 'queued', message: null, error_code: null,
        can_supplement: false, supplemental_input_used: true,
      } : current);
      setSupplementProductName('');
      setSupplementManufacturer('');
      setSupplementReportNumber('');
      setSupplementIngredients([]);
      setQueryError('');
      setQueryRetry((value) => value + 1);
    } catch (error) {
      if (submission.current !== version) return;
      if (error instanceof Error && error.name === 'AbortError') {
        setSupplementUncertain(true);
        setQueryRetry((value) => value + 1);
      } else {
        // The server may have committed before the response was lost; reconcile before allowing another submission.
        setSupplementUncertain(true);
        setQueryRetry((value) => value + 1);
      }
    } finally {
      window.clearTimeout(timeout);
      if (supplementController.current === controller) supplementController.current = null;
      if (submission.current === version) setSupplementing(false);
    }
  }

  const status = result?.status || (handle ? 'queued' : null);
  const researchStatus = result?.report?.scope === 'evidence_review' ? result.report.research.status : null;
  const visibleStatus = researchStatus ? evidenceStatusLabels[researchStatus] : status ? statusLabels[status] : '결과 조회 중';
  const scopeSummary = researchStatus === 'partial'
    ? '공개 페이지 수집 · 일부 근거 조회 · 출처·한계 표시'
    : researchStatus === 'unavailable'
      ? '공개 페이지 수집 · 근거 자료 조회 불가'
      : researchStatus === 'completed'
        ? '공개 페이지 수집 · 공개 근거 조사 · 출처·한계 표시'
        : evidenceReview && !result
          ? '공개 페이지 수집 · 공식 자료·논문 근거 조사 요청'
          : '공개 페이지 수집 · 표시 정보 추출 · 공식 등록 대조';
  const footerText = researchStatus === 'partial'
    ? '근거 조사가 일부 완료되었습니다. 조사 범위와 출처를 함께 확인해 주세요. 점수·구매·복용 권고를 제공하지 않으며, 비회원의 개인 적합성은 미평가입니다.'
    : researchStatus === 'unavailable'
      ? '근거 자료를 조회할 수 없었습니다. 자료의 부재는 제품의 품질이나 효능에 대한 판정이 아닙니다. 점수·구매·복용 권고를 제공하지 않으며, 비회원의 개인 적합성은 미평가입니다.'
      : researchStatus === 'completed'
        ? '공개 자료를 확인한 범위의 근거 조사 보고서입니다. 제품 점수와 구매·복용 권고를 제공하지 않으며, 비회원의 개인 적합성은 미평가입니다.'
        : '이 단계는 제품 정보의 수집·식별 보고서입니다. 제품 점수와 구매·복용 권고를 제공하지 않으며, 비회원의 개인 적합성은 미평가입니다.';
  const missing = result?.missing_fields.length ? result.missing_fields : result?.report?.missing_fields || [];

  return (
    <>
      <a href="#main" className="skip-link">본문 바로가기</a>
      <header className="site-header">
        <a className="brand" href="/" aria-label="Supplement Advisor 홈"><span className="brand-mark" aria-hidden="true">s.</span><span>supplement<span className="brand-light"> advisor</span></span></a>
          <span className="stage-label">{researchStatus ? '근거 조사' : 'M1 · 수집·식별'}</span>
      </header>
      <main id="main">
        <section className="hero" aria-labelledby="page-title">
          <p className="eyebrow">BEFORE YOU BUY</p>
          <h1 id="page-title">구매 전,<br className="mobile-break" /> 근거부터.</h1>
          <p>관심 있는 건강기능식품의 제품 페이지를 모으고,<br className="desktop-break" /> 확인한 정보와 아직 모르는 부분을 구분해 드려요.</p>
        </section>
        <div className="workspace">
          <aside className="input-column" aria-label="제품 조사 입력">
            <section className="input-card">
              <span className="step-label">01 / 제품 페이지</span>
              <h2>어떤 제품이 궁금한가요?</h2>
              <form onSubmit={submit}>
                <label htmlFor="product-url">제품 URL <span className="required">필수</span></label>
                <input id="product-url" type="url" required maxLength={2048} value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/product" autoComplete="off" aria-describedby="url-help" />
                <p className="field-help" id="url-help">누구나 열어 볼 수 있는 판매·제조사 페이지를 입력해 주세요.</p>
                <label htmlFor="product-name">제품명 <span className="optional">선택</span></label>
                <input id="product-name" maxLength={300} value={productName} onChange={(event) => setProductName(event.target.value)} placeholder="알고 있는 제품명이 있다면" autoComplete="off" />
                <label className="research-choice" htmlFor="evidence-review">
                  <input id="evidence-review" type="checkbox" checked={evidenceReview} onChange={(event) => setEvidenceReview(event.target.checked)} />
                  <span><strong>공식 자료·논문 근거도 조사하기</strong><small>조사한 범위와 출처를 보여줍니다. 점수·구매 추천은 하지 않습니다.</small></span>
                </label>
                {submitError && <p className="error" role="alert">{submitError}</p>}
                <button className="primary-button" type="submit" disabled={submitting}>{submitting ? '접수 중…' : '제품 정보 확인하기'}<span aria-hidden="true">↗</span></button>
              </form>
              <p className="session-note">가장 최근 결과의 조회 권한은 이 브라우저 세션에 보관됩니다. 탭을 닫거나 새 조사를 시작하면 이전 결과에 접근하지 못할 수 있습니다.</p>
              {storageWarning && <p className="error" role="status">브라우저 저장소를 사용할 수 없습니다. 새로고침하면 현재 결과의 조회 권한이 사라집니다.</p>}
            </section>
            <section className="capabilities" aria-labelledby="capabilities-title">
              <h3 id="capabilities-title">현재 확인할 수 있는 범위</h3>
              <p>{scopeSummary}</p>
              {capabilityError ? <><p className="small muted">연동 상태를 확인하지 못했습니다.</p><button className="text-button" onClick={() => setCapabilityRetry((value) => value + 1)}>연동 상태 재확인</button></> : capabilities ? <dl>
                <div><dt>표시 정보 자동 추출</dt><dd>{capabilities.openai === 'not_configured' ? '미설정 · 사용 불가' : '설정됨 · 실제 연결 미확인'}</dd></div>
                <div><dt>식품안전나라 등록 대조</dt><dd>{capabilities.food_safety === 'not_configured' ? '미설정 · 사용 불가' : '설정됨 · 실제 연결 미확인'}</dd></div>
              </dl> : <p className="small muted" role="status">연동 상태 확인 중…</p>}
              <p className="small muted">미설정인 기능은 수행하지 않으며, 보고서에 확인 불가로 표시합니다.</p>
            </section>
          </aside>

          <section className="result-card" aria-label={researchStatus ? '근거 조사 결과' : '제품 수집 결과'} aria-busy={polling || submitting}>
            {handle && <div className="result-status"><p role="status" aria-live="polite"><span className={polling ? 'status-dot pulsing' : 'status-dot'} />{visibleStatus}</p><button className="text-button" onClick={reset}>화면에서 지우기</button></div>}
            {queryError && <div className="error-box" role="alert"><p>{queryError}</p><button className="secondary-button" onClick={() => setQueryRetry((value) => value + 1)}>조회 다시 시도</button></div>}
            {result?.message && <p className={result.status === 'failed' ? 'error-box' : 'notice'} role="status">{result.message}</p>}
            {result?.report?.scope === 'evidence_review' ? <ResearchReportView result={result.report} missing={missing} /> : result?.report?.scope === 'collection_only' ? <Report report={result.report} missing={missing} /> : status === 'failed' ? <div className="empty-state compact"><h2>수집 결과가 없습니다</h2><p>제품 페이지의 공개 여부를 확인하거나 다른 제품 URL로 다시 시도해 주세요.</p>{missing.length > 0 && <p>필요한 정보: {missing.map(missingLabel).join(' · ')}</p>}</div> : result?.status === 'needs_input' ? <div className="empty-state compact"><h2>기초 수집 결과가 없습니다</h2><p>이 단계에 저장된 제품 정보가 없습니다. 추가 정보 입력 여부와 관계없이 없는 수집 결과를 추정하지 않습니다.</p>{missing.length > 0 && <p>확인에 필요한 정보: {missing.map(missingLabel).join(' · ')}</p>}</div> : <div className="empty-state">
              <div className="document-symbol" aria-hidden="true"><span /><span /><span /></div>
              <p className="eyebrow">YOUR EVIDENCE, CLEARLY</p>
              <h2>{submitting ? '조사를 접수하고 있어요' : handle ? '제품 정보를 확인하고 있어요' : '하나의 보고서로, 차분하게'}</h2>
              <p>{handle ? '페이지를 수집하고 확인 가능한 표시 정보를 정리합니다. 완료되면 여기에 결과를 표시합니다.' : '제품 URL을 입력하면 표시 정보, 출처, 확인하지 못한 내용을 이곳에서 볼 수 있어요.'}</p>
              <ol className="flow"><li><span>1</span>공개 페이지 수집</li><li><span>2</span>표시·등록 정보 확인</li><li><span>3</span>출처와 한계 정리</li></ol>
            </div>}
            {result?.status === 'needs_input' && result.supplemental_input_used && <p className="notice" role="status">추가 정보 입력을 한 번 사용했습니다. 정보가 더 필요해도 다시 요청하지 않으며, 확인한 범위와 한계를 보고서에 표시합니다.</p>}
            {result?.status === 'needs_input' && result.can_supplement && !result.supplemental_input_used && supplementUncertain && <div className="notice" role="status"><p>추가 정보 접수 여부를 다시 확인하고 있습니다. 중복 입력을 막기 위해 잠시 입력 폼을 숨겼습니다.</p>{queryError && <button className="secondary-button" onClick={() => setQueryRetry((value) => value + 1)}>상태 다시 확인</button>}</div>}
            {result?.status === 'needs_input' && result.can_supplement && !result.supplemental_input_used && !supplementUncertain && <section className="supplement-card" aria-labelledby="supplement-title">
              <p className="eyebrow">ONE-TIME FOLLOW-UP</p>
              <h3 id="supplement-title">알고 있는 정보를 한 번 보태 주세요</h3>
              <p className="small">{missing.length ? `현재 필요한 정보: ${missing.map(missingLabel).join(' · ')}. ` : ''}아는 항목만 선택해 입력하면 공식 등록 정보를 다시 대조합니다. 각 항목은 선택이며, 모르면 비워 두세요.</p>
              <p className="small muted">이 추가 입력은 한 묶음만 제출할 수 있습니다. 제조사나 신고번호가 불확실하면 추측하지 말고 건너뛰어도 됩니다.</p>
              <p className="small muted">성분 목록을 입력하면 보고서의 기존 성분 목록을 이번에 입력한 목록으로 바꿉니다. 기존 성분도 유지하려면 함께 입력해 주세요.</p>
              <form onSubmit={submitSupplement}>
                <label htmlFor="supplement-product-name">제품명 <span className="optional">선택</span></label>
                <input id="supplement-product-name" maxLength={300} value={supplementProductName} onChange={(event) => setSupplementProductName(event.target.value)} autoComplete="off" />
                <label htmlFor="supplement-manufacturer">제조사 <span className="optional">선택</span></label>
                <input id="supplement-manufacturer" maxLength={300} value={supplementManufacturer} onChange={(event) => setSupplementManufacturer(event.target.value)} autoComplete="off" />
                <label htmlFor="supplement-report-number">품목제조 신고번호 <span className="optional">선택</span></label>
                <input id="supplement-report-number" type="text" inputMode="numeric" pattern="[0-9]*" maxLength={100} value={supplementReportNumber} onChange={(event) => setSupplementReportNumber(event.target.value)} aria-describedby="supplement-report-number-help" autoComplete="off" />
                <p className="field-help" id="supplement-report-number-help">숫자만 입력하며 맨 앞의 0도 보존합니다.</p>
                <div className="ingredient-entry-heading"><h4>성분·함량 표시 <span className="optional">선택</span></h4><button className="secondary-button" type="button" onClick={() => setSupplementIngredients((items) => [...items, emptyIngredient()])}>성분 추가</button></div>
                {supplementIngredients.map((ingredient, index) => <fieldset className="ingredient-entry" key={index}>
                  <legend>성분 {index + 1}</legend>
                  <button className="text-button remove-ingredient" type="button" aria-label={`성분 ${index + 1} 삭제`} onClick={() => setSupplementIngredients((items) => items.filter((_, itemIndex) => itemIndex !== index))}>삭제</button>
                  <label htmlFor={`supplement-ingredient-name-${index}`}>성분 이름</label>
                  <input id={`supplement-ingredient-name-${index}`} maxLength={150} value={ingredient.name} onChange={(event) => setSupplementIngredients((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))} autoComplete="off" />
                  <label htmlFor={`supplement-ingredient-amount-${index}`}>표시 함량 <span className="optional">선택</span></label>
                  <div className="amount-fields">
                    <input id={`supplement-ingredient-amount-${index}`} maxLength={100} value={ingredient.amount} onChange={(event) => setSupplementIngredients((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, amount: event.target.value } : item))} placeholder="표시된 그대로" autoComplete="off" />
                    <select aria-label={`성분 ${index + 1} 단위`} value={ingredient.unit} onChange={(event) => setSupplementIngredients((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, unit: event.target.value } : item))}>
                      <option value="">미확인</option><option value="mg">mg</option><option value="μg">μg</option><option value="g">g</option><option value="IU">IU</option><option value="CFU">CFU</option><option value="기타">기타</option>
                    </select>
                  </div>
                  {ingredient.unit === '기타' && <><label htmlFor={`supplement-ingredient-unit-${index}`}>단위 직접 입력</label><input id={`supplement-ingredient-unit-${index}`} maxLength={100} value={ingredient.otherUnit} onChange={(event) => setSupplementIngredients((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, otherUnit: event.target.value } : item))} /></>}
                  <label htmlFor={`supplement-ingredient-basis-${index}`}>섭취 기준 <span className="optional">선택</span></label>
                  <input id={`supplement-ingredient-basis-${index}`} maxLength={200} value={ingredient.basis} onChange={(event) => setSupplementIngredients((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, basis: event.target.value } : item))} placeholder="예: 1일 섭취량" autoComplete="off" />
                </fieldset>)}
                {supplementError && <p className="error" role="alert">{supplementError}</p>}
                <button className="primary-button" type="submit" disabled={supplementing || supplementUncertain}>{supplementing ? '추가 정보를 접수하고 있어요…' : '추가 정보 제출하기'}<span aria-hidden="true">↗</span></button>
              </form>
              <p className="small muted">성분 이름이 비어 있는 행은 제출하지 않습니다. 함량이나 단위가 없으면 그대로 비워 두며, 값을 계산하거나 변환하지 않습니다.</p>
            </section>}
          </section>
        </div>
      </main>
      <footer>{footerText}</footer>
    </>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
