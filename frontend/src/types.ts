export type AnalysisStatus = 'queued' | 'running' | 'needs_input' | 'completed' | 'failed';

export type AnalysisHandle = { id: string; access_token: string };

export type Check = {
  name: string;
  status: 'verified' | 'unverified' | 'unavailable' | 'not_applicable';
  detail: string;
  source_ids: string[];
};

export type OfficialEvidence = {
  field: string;
  page_value: string | null;
  official_value: string | null;
  outcome: 'match' | 'conflict' | 'missing';
  source_ids: string[];
};

export type OfficialCandidate = { record: Record<string, unknown>; source_id: string };

export type OfficialQuery = {
  field: string;
  value: string;
  total_count: number | null;
  returned_count: number;
  truncated: boolean;
};

export type OfficialMatch = {
  state: 'matched' | 'candidate' | 'unverified' | 'unknown';
  reason: string;
  reasons: string[];
  evidence: OfficialEvidence[];
  candidates: OfficialCandidate[];
  queries: OfficialQuery[];
  matched_record: Record<string, unknown> | null;
  name_difference?: { page_name: string; official_name: string };
};

export type SupplementIngredient = {
  name: string;
  amount: string | null;
  unit: string | null;
  basis: string | null;
};

export type CollectionReport = {
  scope: 'collection_only';
  summary: string;
  product: {
    name: string | null;
    submitted_name?: string | null;
    manufacturer: string | null;
    report_number?: string | null;
    field_sources?: { name?: string; manufacturer?: string; report_number?: string };
  };
  claims: string[];
  ingredients: (SupplementIngredient & { source_id?: string | null })[];
  sources: {
    id: string;
    url: string;
    title: string;
    kind: string;
    retrieved_at: string;
    excerpt: string;
    document_id?: string | null;
    version?: string | null;
  }[];
  checks: Check[];
  official_match?: OfficialMatch;
  limitations: string[];
  score: null;
  verdict: 'hold';
  missing_fields?: string[];
};

export type ResearchRoleId = 'composition' | 'claims' | 'personal_fit' | 'safety' | 'official_quality';

export type ResearchFinding = {
  statement: string;
  status: 'supported' | 'contradicted' | 'mixed' | 'not_assessable';
  source_ids: string[];
  quotes: { source_id: string; excerpt: string }[];
  applicability: 'ingredient_only' | 'product_label' | 'product_applicable' | 'unassessed';
};

export type ResearchRole = {
  role: ResearchRoleId;
  status: 'completed' | 'partial' | 'insufficient_evidence' | 'not_applicable' | 'unavailable' | 'failed';
  question: string;
  findings: ResearchFinding[];
  missing_information: string[];
  reasons: string[];
};

export type ResearchSource = {
  id: string;
  kind: 'official' | 'research' | 'discovery';
  title: string;
  url: string;
  retrieved_at: string;
  provider: string;
  document_id?: string | null;
  pmid?: string | null;
  doi?: string | null;
  published_at?: string | null;
  access_scope: 'discovery' | 'abstract' | 'document';
  excerpt: string;
};

export type ResearchResult = {
  status: 'completed' | 'partial' | 'unavailable';
  roles: ResearchRole[];
  sources: ResearchSource[];
  limitations: string[];
  termination_reason: string | null;
  decisions: { role?: ResearchRoleId | 'supervisor'; action?: string; reason?: string }[];
  usage: { total?: number; by_role?: Record<string, number> | null; attribution?: string };
};

export const evidenceStatusLabels: Record<ResearchResult['status'], string> = {
  completed: '근거 조사 완료',
  partial: '근거 조사 일부 완료',
  unavailable: '근거 자료 조회 불가',
};

export type EvidenceReport = Omit<CollectionReport, 'scope'> & {
  scope: 'evidence_review';
  collection_report: CollectionReport | Record<string, unknown>;
  research: ResearchResult;
  score: null;
  verdict: 'hold';
};

export type AnalysisReport = CollectionReport | EvidenceReport;

export type AnalysisResult = {
  id: string;
  status: AnalysisStatus;
  product_name: string | null;
  report: AnalysisReport | null;
  error_code: string | null;
  message: string | null;
  missing_fields: string[];
  can_supplement: boolean;
  supplemental_input_used: boolean;
  created_at: string;
  updated_at: string;
};

export const statusLabels: Record<AnalysisStatus, string> = {
  queued: '수집 대기 중',
  running: '제품 정보 확인 중',
  needs_input: '추가 정보 확인 필요',
  completed: '수집 보고서 준비됨',
  failed: '수집을 마치지 못했어요',
};

export function isHandle(value: unknown): value is AnalysisHandle {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<AnalysisHandle>;
  return typeof item.id === 'string'
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(item.id)
    && typeof item.access_token === 'string'
    && item.access_token.length > 0
    && item.access_token.length <= 256;
}

export function isPending(status: AnalysisStatus) {
  return status === 'queued' || status === 'running';
}

export function missingLabel(field: string) {
  return ({
    product_name: '제품명', manufacturer: '제조사', ingredient_label: '성분·함량 표시',
    ingredients: '성분·함량 표시', report_number: '품목제조 신고번호',
    product_url: '제품 페이지 주소', ingredient_amount_basis: '성분 함량의 섭취 기준', formulation: '제품 제형',
  } as Record<string, string>)[field] || field;
}
