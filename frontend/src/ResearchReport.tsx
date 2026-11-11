import { missingLabel, type CollectionReport, type EvidenceReport, type ResearchRole, type ResearchSource } from './types';
import { Report } from './Report';

const roleLabels = {
  composition: '성분·함량 표시',
  claims: '기능성·광고 근거',
  personal_fit: '개인 적합성',
  safety: '안전성',
  official_quality: '공식 정보·품질',
} as const;
const decisionActorLabels = { ...roleLabels, supervisor: '조사 범위 선택' } as const;

const roleStatusLabels = {
  completed: '검토 완료', partial: '일부 검토', insufficient_evidence: '근거 부족',
  not_applicable: '미평가', unavailable: '조회 불가', failed: '완료하지 못함',
} as const;

const findingStatusLabels = {
  supported: '뒷받침하는 자료', contradicted: '반대되는 자료', mixed: '자료가 엇갈림', not_assessable: '판단할 근거 없음',
} as const;

const scopeLabels = { discovery: '검색 결과', abstract: '초록', document: '문서 본문' } as const;
const sourceKindLabels = { official: '공식 자료', research: '연구 자료', discovery: '검색 결과' } as const;
const reasonLabels: Record<string, string> = {
  not_selected_by_supervisor: '이번 조사 범위에 포함되지 않았습니다.',
  role_not_completed: '이 역할의 검토를 마치지 못했습니다.',
  invalid_role_result: '결과 형식을 확인할 수 없어 근거로 표시하지 않았습니다.',
  action_limit: '허용된 조사 횟수에 도달했습니다.',
  snapshot_invalid: '저장된 조사 상태를 확인할 수 없습니다.',
  snapshot_incompatible: '저장된 조사 상태가 현재 자료와 일치하지 않습니다.',
  unknown_interrupted: '중단 당시 진행 상태를 확인할 수 없어 다시 요청하지 않았습니다.',
};

function sourceLink(value: string) {
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}

function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '조회 시점 미확인' : date.toLocaleString('ko-KR');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isCollectionReport(value: EvidenceReport['collection_report']): value is CollectionReport {
  if (!isRecord(value) || value.scope !== 'collection_only' || typeof value.summary !== 'string'
    || !isStringArray(value.claims) || !Array.isArray(value.ingredients)
    || !Array.isArray(value.sources) || !Array.isArray(value.checks)
    || !isStringArray(value.limitations) || value.score !== null || value.verdict !== 'hold') return false;
  const product = value.product;
  if (!isRecord(product)) return false;
  if (!['name', 'manufacturer'].every((key) =>
    product[key] === null || typeof product[key] === 'string')) return false;
  if (product.report_number !== undefined && product.report_number !== null
    && typeof product.report_number !== 'string') return false;

  const ingredientsValid = value.ingredients.every((item) => isRecord(item)
    && typeof item.name === 'string'
    && (item.amount === null || typeof item.amount === 'string')
    && (item.unit === null || typeof item.unit === 'string')
    && (item.basis === null || typeof item.basis === 'string'));
  const sourcesValid = value.sources.every((item) => isRecord(item)
    && ['id', 'url', 'title', 'kind', 'retrieved_at', 'excerpt'].every((key) => typeof item[key] === 'string'));
  const checksValid = value.checks.every((item) => isRecord(item)
    && typeof item.name === 'string' && typeof item.detail === 'string'
    && ['verified', 'unverified', 'unavailable', 'not_applicable'].includes(String(item.status))
    && isStringArray(item.source_ids));
  if (!ingredientsValid || !sourcesValid || !checksValid) return false;

  if (value.official_match !== undefined) {
    const match = value.official_match;
    if (!isRecord(match) || !['matched', 'candidate', 'unverified', 'unknown'].includes(String(match.state))
      || typeof match.reason !== 'string' || !isStringArray(match.reasons)
      || !Array.isArray(match.evidence) || !Array.isArray(match.candidates) || !Array.isArray(match.queries)
      || (match.matched_record !== null && !isRecord(match.matched_record))) return false;
    if (!match.evidence.every((item) => isRecord(item) && typeof item.field === 'string'
      && (item.page_value === null || typeof item.page_value === 'string')
      && (item.official_value === null || typeof item.official_value === 'string')
      && ['match', 'conflict', 'missing'].includes(String(item.outcome)) && isStringArray(item.source_ids))
      || !match.candidates.every((item) => isRecord(item) && typeof item.source_id === 'string' && isRecord(item.record))
      || !match.queries.every((item) => isRecord(item) && typeof item.field === 'string' && typeof item.value === 'string'
        && (item.total_count === null || typeof item.total_count === 'number')
        && typeof item.returned_count === 'number' && typeof item.truncated === 'boolean')) return false;
    if (match.name_difference !== undefined && (!isRecord(match.name_difference)
      || typeof match.name_difference.page_name !== 'string' || typeof match.name_difference.official_name !== 'string')) return false;
  }
  return true;
}

function RoleCard({ role, sources }: { role: ResearchRole; sources: ResearchSource[] }) {
  const sourceIds = new Set(sources.map((source) => source.id));
  return <article className="research-role">
    <div className="research-role-heading">
      <h4>{roleLabels[role.role]}</h4>
      <span className={`badge research-${role.status}`}>{roleStatusLabels[role.status]}</span>
    </div>
    {role.question && <p className="research-question">{role.question}</p>}
    {role.role === 'personal_fit' && role.status === 'not_applicable' && <p className="small muted">비회원의 개인 적합성은 평가하지 않았습니다.</p>}
    {role.reasons.length > 0 && <ul className="research-reasons">{role.reasons.map((reason, index) => <li key={`${reason}-${index}`}>{reasonLabels[reason] || reason}</li>)}</ul>}
    {role.missing_information.length > 0 && <p className="small muted">추가로 확인할 정보: {role.missing_information.join(' · ')}</p>}
    {role.findings.map((finding, index) => <section className="research-finding" key={`${finding.statement}-${index}`}>
      <p>{finding.statement}</p>
      <div className="research-finding-meta"><span>{findingStatusLabels[finding.status]}</span>
        <span>{finding.applicability === 'ingredient_only' ? '원료 연구 범위' : finding.applicability === 'product_label' ? '제품 표시 범위' : finding.applicability === 'product_applicable' ? '제품 적용 근거' : '제품 적용 여부 미확인'}</span>
      </div>
      {finding.applicability === 'ingredient_only' && <p className="small muted">제품에 적용되는 근거로 해석하지 않습니다.</p>}
      {finding.quotes.map((quote, quoteIndex) => <blockquote key={`${quote.source_id}-${quoteIndex}`}>{quote.excerpt}</blockquote>)}
      {finding.source_ids.filter((id) => sourceIds.has(id)).map((id) => <a className="research-citation" key={id} href={`#research-source-${encodeURIComponent(id)}`}>출처 {id}</a>)}
    </section>)}
  </article>;
}

function SourceCard({ source }: { source: ResearchSource }) {
  const href = sourceLink(source.url);
  return <article className="source research-source" id={`research-source-${encodeURIComponent(source.id)}`}>
    <div className="source-meta"><span>{sourceKindLabels[source.kind]}</span><span>{scopeLabels[source.access_scope]} · {dateLabel(source.retrieved_at)}</span></div>
    <h4>{href ? <a href={href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{source.title || '출처 페이지'} <span aria-label="새 창">↗</span></a> : source.title || '출처 페이지'}</h4>
    {(source.published_at || source.document_id || source.pmid || source.doi) && <p className="source-version">
      {source.published_at && <>발행일: <strong>{source.published_at}</strong></>}
      {source.document_id && <>공식 자료 번호: <strong>{source.document_id}</strong></>}
      {source.pmid && <>PMID: <strong>{source.pmid}</strong></>}
      {source.doi && <>DOI: <strong>{source.doi}</strong></>}
    </p>}
    {source.excerpt && <blockquote>{source.excerpt}</blockquote>}
    <small>출처 ID: {source.id}</small>
  </article>;
}

export function ResearchReport({ result, missing }: { result: EvidenceReport; missing: string[] }) {
  const research = result.research;
  const collectionReport = isCollectionReport(result.collection_report) ? result.collection_report : null;
  const selectedDecisions = research.decisions.filter((item) => item.role && item.reason);
  const usageAvailable = typeof research.usage.total === 'number'
    && typeof research.usage.by_role === 'object' && research.usage.by_role !== null;
  return <>
    <div className="report-intro">
      <p className="eyebrow">EVIDENCE REVIEW</p>
      <h2>근거 조사 결과</h2>
      <p>{research.status === 'partial' ? '일부 공개 근거만 확인했습니다' : research.status === 'unavailable' ? '근거 자료를 조회할 수 없었습니다' : '공개 자료를 조사한 범위를 정리했습니다'}</p>
      <div className="scope-tags"><span>점수 없음 · 구매 추천 없음</span><span>개인 적합성 미평가</span></div>
    </div>

    {missing.length > 0 && <section className="notice" aria-labelledby="research-missing-title">
      <h3 id="research-missing-title">함께 확인할 정보</h3><p>{missing.map(missingLabel).join(' · ')}</p>
      <p className="small">정보가 부족하다는 뜻이며, 제품의 품질이 낮다는 뜻은 아닙니다.</p>
    </section>}

    {collectionReport
      ? <details className="research-collection-details"><summary>기초 수집 결과 자세히 보기</summary><p className="research-collection-summary">{collectionReport.summary}</p><Report report={collectionReport} missing={collectionReport.missing_fields || []} /></details>
      : <section className="notice" role="status"><h3>기초 수집 결과가 없습니다</h3><p>저장된 제품 표시 정보를 찾을 수 없습니다. 없는 수집 결과를 추정하지 않습니다.</p></section>}

    <section className="report-section" aria-labelledby="research-roles-title">
      <h3 id="research-roles-title">검토한 범위와 결과</h3>
      <div className="research-roles">{research.roles.map((role) => <RoleCard role={role} sources={research.sources} key={role.role} />)}</div>
    </section>

    {selectedDecisions.length > 0 && <section className="report-section" aria-labelledby="research-decisions-title">
      <h3 id="research-decisions-title">조사 범위와 이유</h3>
      <ul className="plain-list research-decisions">{selectedDecisions.map((item, index) => <li key={`${item.role}-${index}`}><strong>{decisionActorLabels[item.role!]}</strong>: {item.reason}</li>)}</ul>
    </section>}

    <section className="report-section" aria-labelledby="research-sources-title">
      <h3 id="research-sources-title">출처와 조회 시점</h3>
      {research.sources.length > 0 ? <div className="sources">{research.sources.map((source) => <SourceCard source={source} key={source.id} />)}</div> : <p className="muted">표시할 수 있는 출처가 없습니다.</p>}
    </section>

    {research.limitations.length > 0 && <section className="report-section limitations" aria-labelledby="research-limitations-title">
      <h3 id="research-limitations-title">보고서의 한계</h3><ul>{research.limitations.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
    </section>}

    {usageAvailable && <p className="small muted research-usage">수집·조사 요청 시도 {research.usage.total}회 (예약 기준, M1 수집 포함)</p>}
  </>;
}
