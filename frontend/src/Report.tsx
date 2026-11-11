import { missingLabel, type CollectionReport, type OfficialMatch } from './types';

const checkLabels = {
  verified: '확인됨', unverified: '미확인', unavailable: '확인 불가', not_applicable: '미평가',
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

function collectedAt(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '수집일 미확인' : date.toLocaleString('ko-KR');
}

const officialStateLabels: Record<OfficialMatch['state'], string> = {
  matched: '공식 등록 확인',
  candidate: '공식 후보 있음 · 추가 확인 필요',
  unverified: '공식 등록 미확인',
  unknown: '공식 조회 미완료',
};
const nameDifferenceHeadline = '공식 등록정보 대조 확인 — 판매명 차이 있음';

const outcomeLabels = { match: '일치', conflict: '모순', missing: '누락' } as const;
const fieldLabels: Record<string, string> = {
  PRDLST_NM: '공식 제품명', BSSH_NM: '공식 제조사', PRDLST_REPORT_NO: '공식 신고번호',
  LAST_UPDT_DTM: '공식 자료 변경일', PRDLST_NM_ALIAS: '제품명 별칭',
  product_name: '제품명', name: '제품명', manufacturer: '제조사', report_number: '품목제조 신고번호',
  ingredient: '성분', ingredients: '성분', amount: '함량',
  additional_ingredient: '추가 성분 근거',
  RAWMTRL_NM: '주요 기능성 원료', major_ingredient: '주요 기능성 원료', ingredient_amount_basis: '함량 및 기준',
  ingredient_amount: '함량', dosage_form: '제형',
};

function readableField(field: string) {
  return fieldLabels[field] || field.replaceAll('_', ' ');
}

function recordEntries(record: Record<string, unknown>) {
  return Object.entries(record).filter(([, value]) =>
    typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
  ).filter(([key]) => !/(url|auth|key|token|service.?key)/i.test(key));
}

function OfficialMatchDetails({ match }: { match: OfficialMatch }) {
  return (
    <section className={`report-section official-match state-${match.state}`} aria-labelledby="official-match-title">
      <h3 id="official-match-title">{match.state === 'matched' && match.name_difference ? nameDifferenceHeadline : '공식 등록 후보 대조'}</h3>
      <div className={`official-state state-${match.state}`} role="status">
        <strong>{match.state === 'matched' && match.name_difference ? nameDifferenceHeadline : officialStateLabels[match.state]}</strong>
        <p>{match.reason || '공식 자료와 제품 표시를 대조한 결과를 확인해 주세요.'}</p>
      </div>
      {match.name_difference && <div className="name-difference" aria-label="판매명과 공식 등록명 차이">
        <dl>
          <div><dt>판매 페이지 제품명</dt><dd>{match.name_difference.page_name}</dd></div>
          <div><dt>공식 등록 제품명</dt><dd>{match.name_difference.official_name}</dd></div>
        </dl>
        <p className="small">두 이름은 원문 그대로 표시했습니다. 제품명 차이는 아래 이름 대조 항목의 모순이며, 주요 원료의 모순과는 구분됩니다.</p>
      </div>}
      {match.evidence.some((item) => item.outcome === 'missing' && ['ingredient_amount_basis', 'ingredient_amount', 'formulation', 'dosage_form'].includes(item.field)) && <p className="small muted comparison-limits">
        {match.evidence.some((item) => item.outcome === 'missing' && ['ingredient_amount_basis', 'ingredient_amount'].includes(item.field)) && '함량·섭취 기준은 비교 근거가 부족합니다. '}
        {match.evidence.some((item) => item.outcome === 'missing' && ['formulation', 'dosage_form'].includes(item.field)) && '제형은 페이지에서 확인되지 않았습니다.'}
      </p>}
      {match.state === 'candidate' && <p className="small candidate-note">후보는 같은 제품인지 더 확인하기 위한 공식 자료입니다. 구매 추천이나 제품 품질 판정이 아닙니다.</p>}
      {match.state === 'unknown' && <p className="small muted">공식 조회가 끝나지 않았습니다. 등록 여부를 판단할 수 없습니다.</p>}
      {match.state === 'unverified' && <p className="small muted">조회했지만 일치 확인에 필요한 정보가 부족하거나 후보가 확인되지 않았습니다. 미등록 또는 불법이라는 뜻은 아닙니다.</p>}
      {match.evidence.length > 0 && <div className="table-scroll official-evidence-wrap">
        <table className="official-evidence">
          <caption>제품 페이지 표시와 공식 자료의 항목별 비교</caption>
          <thead><tr><th scope="col">항목</th><th scope="col">제품 페이지 표시</th><th scope="col">공식 자료</th><th scope="col">비교</th></tr></thead>
          <tbody>{match.evidence.map((item, index) => <tr key={`${item.field}-${index}`}>
            <th scope="row">{readableField(item.field)}</th>
            <td>{item.page_value || '누락'}</td><td>{item.official_value || '누락'}</td>
            <td><span className={`evidence-outcome ${item.outcome}`}>{outcomeLabels[item.outcome]}</span>
              {item.source_ids.length > 0 && <span className="evidence-sources">{item.source_ids.map((id, sourceIndex) => <a key={`${id}-${sourceIndex}`} href={`#source-${encodeURIComponent(id)}`}>{id}</a>)}</span>}
            </td>
          </tr>)}</tbody>
        </table>
      </div>}

      {match.matched_record && <article className="official-record">
        <h4>대조된 공식 등록 자료</h4>
        <dl>{recordEntries(match.matched_record).map(([key, value]) => <div key={key}><dt>{readableField(key)}</dt><dd>{String(value)}</dd></div>)}</dl>
        <p className="small muted">공식 신고번호는 위 공식 자료에만 표시하며, 제품 페이지에 입력·추출된 번호를 대신하지 않습니다.</p>
      </article>}

      {match.candidates.length > 0 && <div className="official-candidates">
        <h4>검토할 공식 후보 {match.candidates.length}건</h4>
        {match.candidates.map((candidate, index) => <article className="official-record candidate-record" key={`${candidate.source_id}-${index}`}>
          <p className="small">{match.state === 'matched' ? '공식 검색 결과 · 대조 기록' : '후보 자료 · 동일 제품 추가 확인 필요'}</p>
          <dl>{recordEntries(candidate.record).map(([key, value]) => <div key={key}><dt>{readableField(key)}</dt><dd>{String(value)}</dd></div>)}</dl>
          <a href={`#source-${encodeURIComponent(candidate.source_id)}`}>출처 {candidate.source_id}</a>
        </article>)}
      </div>}

      {match.queries.length > 0 && <details className="official-queries">
        <summary>공식 검색 범위 {match.queries.length}건 보기</summary>
        <ul>{match.queries.map((query, index) => <li key={`${query.field}-${index}`}>
          <strong>{readableField(query.field)}</strong>: {query.value} · 전체 {query.total_count === null ? '미확인' : `${query.total_count}건`} · 반환 {query.returned_count}건{query.truncated ? ' · 결과가 잘렸습니다' : ''}
        </li>)}</ul>
      </details>}
    </section>
  );
}

export function Report({ report, missing }: { report: CollectionReport; missing: string[] }) {
  const userProvided = (sourceId: string | undefined) => sourceId === 'user-input';
  return (
    <>
      <div className="report-intro">
        <p className="eyebrow">COLLECTION REPORT</p>
        <h2>확인한 정보와 남은 질문</h2>
        <p>{report.summary}</p>
        <div className="scope-tags"><span>제품 점수 미산정</span><span>개인 적합성 미평가</span></div>
      </div>

      {missing.length > 0 && <section className="notice" aria-labelledby="missing-title">
        <h3 id="missing-title">함께 확인할 정보</h3>
        <p>{missing.map(missingLabel).join(' · ')}</p>
        <p className="small">정보가 부족하다는 뜻이며, 제품의 품질이 낮다는 뜻은 아닙니다.</p>
      </section>}

      <section className="report-section" aria-labelledby="product-title">
        <h3 id="product-title">제품 표시 정보</h3>
        <dl className="product-fields">
          <div><dt>확인된 제품명</dt><dd>{report.product.name || '미확인'}{userProvided(report.product.field_sources?.name) && <small> (사용자 추가 입력)</small>}</dd></div>
          {report.product.submitted_name && <div><dt>입력한 제품명</dt><dd>{report.product.submitted_name} <small>(사용자 입력)</small></dd></div>}
          <div><dt>제조사</dt><dd>{report.product.manufacturer || '미확인'}{userProvided(report.product.field_sources?.manufacturer) && <small> (사용자 추가 입력)</small>}</dd></div>
          <div><dt>품목제조 신고번호</dt><dd>{report.product.report_number || '미확인'}{userProvided(report.product.field_sources?.report_number) && <small> (사용자 추가 입력)</small>}</dd></div>
        </dl>
      </section>

      {report.official_match && <OfficialMatchDetails match={report.official_match} />}

      <section className="report-section" aria-labelledby="checks-title">
        <h3 id="checks-title">확인 내역</h3>
        <div className="checks">
          {report.checks.map((check, index) => <article className="check" key={`${check.name}-${index}`}>
            <div className="check-heading"><h4>{check.name}</h4><span className={`badge ${check.status}`}>{checkLabels[check.status]}</span></div>
            <p>{check.detail}</p>
            {check.source_ids.length > 0 && <p className="small citations">출처 {check.source_ids.map((id, index) =>
              <a key={`${id}-${index}`} href={`#source-${encodeURIComponent(id)}`}>{id}</a>
            )}</p>}
          </article>)}
        </div>
      </section>

      <section className="report-section" aria-labelledby="ingredients-title">
        <h3 id="ingredients-title">성분·함량 표시</h3>
        {report.ingredients.length ? <div className="table-scroll"><table>
          <caption className="sr-only">수집한 성분, 함량과 섭취 기준</caption>
          <thead><tr><th scope="col">성분</th><th scope="col">표시 함량</th><th scope="col">섭취 기준</th></tr></thead>
          <tbody>{report.ingredients.map((item, index) => <tr key={`${item.name}-${index}`}>
            <th scope="row">{item.name}{userProvided(item.source_id || undefined) && <><br /><small>(사용자 추가 입력)</small></>}</th>
            <td>{item.amount ?? '함량 미확인'}{item.unit ? ` ${item.unit}` : ''}</td>
            <td>{item.basis || '미확인'}</td>
          </tr>)}</tbody>
        </table></div> : <p className="muted">확인된 성분·함량 표시가 없습니다. 없는 값을 추정하지 않습니다.</p>}
      </section>

      <section className="report-section" aria-labelledby="claims-title">
        <h3 id="claims-title">페이지에 표시된 광고 문구</h3>
        {report.claims.length ? <ul className="plain-list">{report.claims.map((claim, index) => <li key={index}>{claim}</li>)}</ul> : <p className="muted">추출된 광고 문구가 없습니다.</p>}
        <p className="small muted">표시 문구의 수집이며, 효능이나 광고의 진위를 확정한 결과가 아닙니다.</p>
      </section>

      <section className="report-section" aria-labelledby="sources-title">
        <h3 id="sources-title">출처와 수집 시점</h3>
        <div className="sources">{report.sources.map((source, index) => {
          const href = sourceLink(source.url);
          const kind = ({ advertising: '제품 페이지·광고', official: '공식 자료', research: '연구 자료', user_input: '사용자 제공' } as Record<string, string>)[source.kind] || '기타 자료';
          return <article className="source" key={`${source.id}-${index}`} id={`source-${encodeURIComponent(source.id)}`}>
            <div className="source-meta"><span>{kind}</span><span>{collectedAt(source.retrieved_at)}</span></div>
            <h4>{href ? <a href={href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{source.title || '출처 페이지'} <span aria-label="새 창">↗</span></a> : source.title || '출처 페이지'}</h4>
            {(source.document_id || source.version) && <p className="source-version">{source.document_id && <>공식 신고번호: <strong>{source.document_id}</strong></>}{source.document_id && source.version && ' · '}{source.version && <>자료 버전·변경일: <strong>{source.version}</strong></>}</p>}
            {source.excerpt && <blockquote>{source.excerpt}</blockquote>}
            <small>출처 ID: {source.id}</small>
          </article>;
        })}</div>
      </section>

      <section className="report-section limitations" aria-labelledby="limitations-title">
        <h3 id="limitations-title">보고서의 한계</h3>
        <ul>{report.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
      </section>
    </>
  );
}
