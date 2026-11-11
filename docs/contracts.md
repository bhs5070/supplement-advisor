# M1: 제품 조사 접수·수집 계약

최신 상태: 사용자가 이후 **“M2 시작하자”**로 M2 착수를 요청했다. 아래 M1 API/보고서 계약은 유지한다. M2-A의 별도 조사 계약은 승인된 docs/superpowers/specs/2026-11-11-m2a-evidence-review-design.md를 따른다. 점수·추천은 후속이다. 이 문서의 과거 보류 문장은 최신 실행 지시가 아니다.

2026-11-07. 초기 기술 선택 이후 첫 세로 기능의 구현 계약이다.

## 범위
비회원 URL 제출 → PostgreSQL 작업 저장 → Redis/Celery 전달 → HTTPX 수집 → LangGraph 수집·표시 정보 추출·공식 제품 대조 → 결과 저장 → 권한 있는 클라이언트 조회.
입력 제품이나 광고가 미확인일 때 점수와 추천을 생성하지 않는다. 이 단계는 전체 5개 전문 Agent 평가가 아니라 수집·식별 검증이다.

## HTTP 계약
- `GET /api/health`: liveness. `GET /api/ready`: DB·broker 연결 확인.
- `GET /api/capabilities`: 설정된 외부 연동 상태. 비밀키·접속 문자열은 제외.
- `POST /api/analyses`: `{url, product_name?: string}`. 공개 HTTP(S), 길이 제한. 202 반환 `{id, access_token, status}`. 토큰은 응답 한 번만 노출한다.
- `GET /api/analyses/{id}`: `X-Analysis-Token`으로 해당 분석만 조회. 잘못된 id/토큰은 동일 404. URL에 토큰을 넣지 않는다.
- 비회원 조회 토큰은 `secrets.token_urlsafe(32)` 생성, DB에는 SHA-256만 저장한다.
- 입력 오류 422. 원문 수집 실패는 분석 결과의 실패·추가 입력 필요 상태로 기록한다.
- 작업 상태: queued, running, needs_input, completed, failed. 수집 단계의 completed는 보고서의 `scope=collection_only`로 명시한다. 제품 평가 완료와 구분한다.
- 결과: `scope`, `summary`, `product`, `claims`, `ingredients`, `sources`, `checks`, `limitations`, `score: null`, `verdict: "hold"`.
- ingredient: `{name, amount: string|null, unit: string|null, basis: string|null}`. μg/mg 변환·없는 값 추정 금지.
- source: `{id, url, title, kind, retrieved_at, excerpt}`. 공식/광고/연구의 종류를 명시한다. excerpt는 짧은 확인 구절만 저장한다.
- check: `{name, status: "verified"|"unverified"|"unavailable"|"not_applicable", detail, source_ids: list[str]}`.
- 실패/추가 입력: `error_code`, `message`, `missing_fields`를 구분한다. 예상 불가한 내부 오류의 상세·URL 쿼리·예외 원문은 사용자나 로그에 그대로 노출하지 않는다.

## Python 모듈 경계
패키지: `src/supplement_advisor/`. 리드가 `config.py`, `schemas.py`, `main.py`, `tasks.py`, `celery_app.py`를 소유한다.

### 수집 담당 소유: `collection.py`, `tests/test_collection.py`
- `CollectionError(code: str, message: str)`; 안전한 사용자 메시지.
- `async collect_page(url: str, *, timeout: float = 15, max_bytes: int = 2_000_000) -> CollectedPage`.
- `CollectedPage` dataclass 필드: `url: str`, `title: str`, `text: str`, `html: str`, `image_urls: list[str]`.
- `async validate_public_url(url: str) -> None`. URL 구조/포트/DNS/public IP 확인. 리디렉션마다 검증, 실제 접속 주소를 검증된 IP에 고정하여 DNS 재바인딩 방지. 환경 프록시 사용 금지. TLS hostname 검증 유지.
- stdlib HTMLParser로 script/style 제외 텍스트·title·이미지 URL을 추출. 이미지 URL은 데이터이며 자동 다운로드하지 않는다.
- 응답 크기·리디렉션·전체 시간 한도 적용, HTML/XHTML만 처리. 웹 데이터는 명령으로 취급하지 않는다.

### DB 담당 소유: `database.py`, `models.py`, `repository.py`, `migrations/**`, `alembic.ini`, `tests/test_repository.py`
- SQLAlchemy 2.x + psycopg. 주 DB PostgreSQL. SQLite는 격리된 단위 테스트에서만 허용한다.
- `make_engine(database_url: str)`, `session_factory(engine)`가 context manager로 쓸 수 있는 Session 팩터리를 반환.
- Analysis 모델: UUID 문자열 id, token_hash, url, product_name nullable, status, report JSON nullable, error_code nullable, message nullable, created_at/updated_at UTC timezone, started_at nullable, completed_at nullable, attempt_count int, raw_file nullable, claim_token nullable, lease_expires_at nullable, active_seconds_reserved float, tool_calls_reserved int, graph_snapshot JSON nullable.
- `create_analysis(session, *, url, product_name, token_hash) -> Analysis`가 id 생성. 함수는 flush, commit은 호출자가 담당.
- `get_analysis(session, analysis_id: str) -> Analysis|None`.
- `claim_analysis(session, analysis_id: str, *, max_attempts: int = 3, lease_seconds: int = 240) -> Analysis|None`: terminal 제외, 원자적으로 running 점유, attempt_count 증가. 새 claim_token으로 오래된 Worker의 결과 덮어쓰기를 막는다. started_at은 첫 실행 시각을 보존한다.
- `finish_analysis(session, analysis_id, *, claim_token, status, report=None, error_code=None, message=None, raw_file=None) -> bool`: 현재 점유 토큰과 유효 lease가 일치할 때만 종료 기록. 실패하면 false.
- `list_dispatchable(session, *, limit: int = 50) -> list[str]`: queued 또는 점유가 만료된 running 작업을 조회. 최대 시도 초과 작업은 claim에서 failed로 정리한다.
- `reserve_budget(session, analysis_id, *, claim_token, seconds, tool_calls, max_seconds=180, max_tool_calls=20) -> bool`: 현재 점유와 누적 예산을 원자적으로 검사·예약한다. 실패한 예약은 차감하지 않는다. 예약 시간은 중단 후 환급하지 않아 crash 후에도 예산을 보존한다.
- `save_snapshot(session, analysis_id, *, claim_token, snapshot) -> bool`: 유효한 점유만 실행 snapshot을 저장한다.
- API 저장 후 큐 발행 실패·Worker 중단의 복구 경로는 작업 통합 담당이 구현하고 검사한다. 240초 lease와 활성 실행 180초 한도는 서로 다른 정책이다. 재시도 시 예산을 새로 주지 않는다. 시도 창 `min(attempt_timeout_seconds, analysis_timeout_seconds)`을 도구 실행 전에 commit해 예약하고 환급하지 않는다. process_analysis Celery prefork hard limit은 같은 창, soft limit은 창보다 1초 작다(기본 60/59초). claim/예약 전 DB 제어 및 큐 대기는 활성 조사와 구분한다.
- 초기 마이그레이션과 env DB URL 사용. 민감 정보 repr/log 금지.
- DB에서 불명확한 작업을 영원히 running으로 두지 않을 재처리 경로 제안·구현. 계약을 바꿔야 하면 리드와 먼저 합의.

### Agent 담당 소유: `agents/**`, `tests/test_agents.py`
- `async run_collection_graph(page: CollectedPage, product_name: str|None, settings, *, checkpointer=None, thread_id: str|None=None) -> dict`.
- 설정 인터페이스(리드 config 제공): `openai_api_key`, `openai_model='gpt-5.6-luna'`, `food_safety_api_key`, `external_timeout_seconds=15`, `analysis_timeout_seconds=180`, `max_tool_calls=20`.
- LangGraph StateGraph로 문서 관찰 → optional Luna 구조화 추출 → optional I0030 실제 조회 → 근거·미검증 보고서 생성. 무키 상태는 명확한 unavailable. 모델 없이 성분·광고 주장을 추측하는 가짜 fallback 금지.
- OpenAI Responses API 구조화 출력(Pydantic), temperature를 임의 설정하지 않는다. max output/calls/time을 제한하고 SDK 자동 재시도 한도를 명시한다.
- page URL/image URL에서 모델이 명령을 따르지 않도록 원문 데이터와 시스템 지시 분리.
- I0030 결과는 제품명만 같다는 이유로 동일 제품 판정 금지. 제조사·신고번호 등 함께 확인. 일치 확인 안 되면 unverified.
- 문헌·등록으로 실제 함량 측정을 주장하지 않는다. 결과는 collection_only, score null, verdict hold. 과거 전체 평가 설계를 deterministic 한 번 호출로 구현했다고 주장하지 않는다.
- 체크포인터는 호출자가 주입. DB 장기 데이터와 실행 snapshot을 구분. 불완전 resume/재시도는 완료로 표시하지 않는다.

## 독립 검증
- 실제 PostgreSQL+Redis+Celery 경로, task 중복 실행, guest token 접근 격리, 악성 URL/리디렉션, 모델·API 미설정, 호출 실패를 검사한다.
- mock 테스트 통과와 실연동 성공은 따로 기록한다.
- 표준 프레임워크 구조를 사용하며 미리 일반화된 플러그인·agent factory·repository base class를 만들지 않는다.


## M1 확장: 권한 있는 비회원 추가 정보 1묶음 — 2026-11-09

사용자가 추가 정보 입력을 M1으로 앞당기기로 선택했다. HTML 텍스트에 신고번호가 없어 공식 동일성 확인을 끝내지 못하는 문제를, 필요한 정보를 한 번 보완해 재대조하는 흐름으로 해결한다. 이미지·회원 기능·점수·추천·전체 평가는 추가하지 않는다.

- `POST /api/analyses/{id}/supplement`: 동일 `X-Analysis-Token` 권한. body `{product_name?: string|null, manufacturer?: string|null, report_number?: string|null, ingredients?: [{name, amount: string|null, unit: string|null, basis: string|null}]}`. identity 최대 300자(번호 최대100자), ingredient name150/amount100/unit100/basis200, 최대50행. 공백을 정리하고 적어도 1개 값 또는 비어 있지 않은 성분행을 요구한다. 신고번호는 문자열 ASCII 숫자로 검증하고 선행 0을 보존하며 특정 고정 길이를 가정하지 않는다. 없는 함량·단위·기준 추정/변환 금지. 선택 성분 값의 공백은 null로 정규화한다. 수동 성분 목록을 제공하면 기존 성분 목록을 대체하므로 화면에서 제출 전에 이를 설명한다.
- 권한 불일치·없는 id·긴 토큰은 기존 조회와 동일404. `needs_input`이고 아직 추가 정보를 받지 않은 분석만 원자적으로 1번 수신한다. 중복·다른 상태는409. 성공202 `{id,status:"queued"}`이며 토큰을 재발급하거나 반환하지 않는다. queued commit 뒤 큐 발행 실패는 기존 beat가 복구한다.
- GET 결과에 `supplemental_input_used: bool`, `can_supplement: bool`을 추가한다. status needs_input + 미사용일 때만 가능하다. 추가 처리 뒤에도 부족하면 needs_input이지만 두 번째 입력을 반복 요청하지 않는다.
- DB `supplemental_input: JSON|null`, `supplemental_received_at: datetime|null` 추가 migration. `accept_supplement(session,id,token_hash,payload)`는 조건부 update로 payload와 시각을 저장하고 queued/오류·완료시각·lease를 정리한다. report/raw_file은 보존하고 graph_snapshot은 새 입력과 맞지 않는 과거 official 결과 재사용을 막도록 비운다. attempt_count/active_seconds_reserved/tool_calls_reserved는 리셋하지 않는다. 사용자 응답 대기는 예약하지 않는다.
- Worker는 추가 입력이 있으면 이미 저장된 report를 기반으로 보완 재대조한다. HTTPX 재수집·실모델 재추출 없이 공식 대조만 필요한 예산을 예약하고 실행한다. 새 claim과 기존 누적 시도/시간/도구 한도·fencing을 유지한다. 기존 raw_file을 보존한다. 추가 처리의 예산 부족·시간 초과·예외로 실패하더라도 이전 수집 report를 지우지 않고 실패 상태·메시지와 함께 조회할 수 있어야 한다.
- Agent 추가 함수 `async run_supplement_graph(report: dict, supplemental_input: dict, settings, *, received_at: str|None=None) -> dict`. settings의 checkpoint/budget hook을 사용하며 별도 fingerprint/version으로 추가입력 재시도에서 완료된 official 결과를 재사용한다. 사용자 identity/성분만 명시적으로 보완하고 나머지 표시 추출값은 보존한다. source `id=user-input`, `kind=user_input`, URL은 빈 문자열(외부 링크 없음), title은 사용자 추가 입력. 사용자가 제공한 값임을 excerpt/limitation/check에 명시하고 seller 원문 추출로 위장하지 않는다.
- 결과 product에 선택적 `field_sources`(name/manufacturer/report_number별 source id)를 제공하고 보완 성분은 source_id를 `user-input`으로 표시한다. 원문 성분을 보완 성분으로 대체하면 사용자 제공 목록임을 명시한다. `공식 등록 대조`의 source_ids는 실제 identity 각 필드가 나온 출처(field_sources)의 합집합과 새 official source로 구성한다. 성분만 보완했으면 기존 판매 페이지 identity 대조이며, 번호만 보완했으면 판매 페이지/사용자 혼합 identity 대조다. verified는 표시한 출처의 identity와 등록자료의 일치이며 실제 함량·효과·개인 안전성의 증명이 아님을 알린다. 기존 seller source를 보존하고 stale official source는 새 결과로 대체한다.
- `missing_fields`에는 공식 동일성에 필요한 report_number 누락도 포함한다. user_input_used 이후 부족하면 확인한 범위와 한계를 알리고 종료하며 추가 요청 폼은 제공하지 않는다.

소유권: API/DB/Worker 담당은 schemas/main/repository/models/tasks/migration 및 관련 tests, Agent 담당은 agents/**+tests/test_agents.py, Frontend 담당은 frontend/**. 공유 계약은 이 항목을 따른다. 실모델 추가 호출 없이 관련 검사·실브라우저 mock 검증·독립 QA를 수행한다.

## 자동 공식 후보 대조 확장 — 2026-11-09

사용자 승인 방향은 URL 원문 → 독립 표시 추출 → 공식 후보 검색 → 다중 근거 대조다. 추가 입력은 자동 실패 시의 기존 1회 fallback이다. 원문 product 필드와 공식 등록 필드를 합치지 않는다.

- 기존 check.status는 유지한다. 새 선택 `official_match` 보고서 객체는 `{state: "matched"|"candidate"|"unverified"|"unknown", reason: string, reasons: string[], evidence: [{field, page_value, official_value, outcome: "match"|"conflict"|"missing", source_ids: string[]}], candidates: [{record: object, source_id: string}], queries: [{field: string, value: string, total_count: number|null, returned_count: number, truncated: boolean}], matched_record: object|null}`다. record에는 원래 API 필드명·값을 보존하고 인증 URL은 저장하지 않는다. source에는 기존 retrieved_at/document_id/version을 사용한다. 기존 보고서는 이 객체가 없어도 표시한다.
- matched만 check verified다. candidate는 동일 제품을 더 확인하기 위한 공식 후보이며 구매 추천이 아니다. unknown은 조회 미완료·인증/차단·예산 문제, unverified는 조회했으나 후보 없음/근거 불충분이다. reason/reasons에는 이 차이를 보존한다.
- 신고번호가 있으면 기존 번호 우선 강한 대조를 유지한다. 번호가 없으면 최대 3개 검색을 예약 후 실행한다. 공백·법인 기호 등 동등 표기와 판매 수량 접미사만 검색용으로 정리하며 product 원문은 변경하지 않는다. 공장명·변형 제품명은 삭제하지 않는다.
- 번호 없는 확인은 제품명·제조사 동등성과 원문에서 확인한 추가 성분/제형/함량 근거의 일치, 모순 없음, 완전한 검색집합에서 단일 후보가 모두 필요하다. 이름만 일치·첫 후보·상위20개 유일성은 확인 근거가 아니다. 추가 근거의 규칙과 한계를 명시한다. API 값을 모델 원문에 역주입하지 않는다.
- total_count를 보존하며 누락되거나 반환 수보다 크면 집합 불완전으로 취급한다. 후보 전체집합을 확보하지 못하면 번호 없는 자동 확인은 금지한다. 서로 다른 변형·복수 동일명/제조사·모순·추가근거 부족은 candidate/unverified로 남긴다.
- matched여도 product.report_number에 공식 번호를 채우지 않는다. 공식 번호는 matched_record와 official source에만 표시한다. 자동 등록 확인이 완료되면 페이지 번호 누락만으로 missing_fields에 report_number를 요구하지 않는다.
- snapshot 버전을 올려 과거 official 판정을 재사용하지 않으며 기존 누적 예산·호출당 예약·claim fencing·시도60초/활성180초/총20회/역할6회를 보존한다. supplement도 동일 판정 DTO와 provenance를 사용한다. API report JSON이므로 DB migration은 요구하지 않는다.

소유권: backend 작성자는 agents/** 및 관련 tests만, frontend 작성자는 frontend/** (types.ts/Report.tsx 포함)만 수정한다. 공유 schemas/API/DB 변경은 리드에게 전달한다. 독립 QA는 작성자와 분리한다.

추가근거 구현 제약: 성분 함량은 API의 내용 필드에서 같은 성분 항목에 결합된 이름·숫자·단위로 비교한다. 신고번호·일자·다른 성분의 숫자를 빌려 일치시키지 않는다. 원문에서 없는 함량을 계산하거나 API의 복용량·진세노사이드 함량과 홍삼농축액 배합비를 같은 측정값으로 취급하지 않는다. 비교 불가능한 자료는 missing이며 충돌하는 동일 측정값은 conflict다. 정확히 어떤 필드를 비교했는지 evidence에 남긴다.

실제 I0030의 원재료 비교는 배합비가 없을 수 있다. 이때 독립 추출된 특징성 부원료가 공식 원재료 전용 필드에 정확한 이름으로 2개 이상 나타나는 것을 보조 근거로 사용할 수 있다. 홍삼·정제수 같은 공통 기본원료 단독 일치는 충분하지 않다. 이 조건도 제품명·제조사·완전한 집합·유일성·모순 없음 조건과 함께 적용하며 제형·함량을 추정하지 않는다. 아가베/용설란 같은 동의어는 추가 검증 없이 동일 처리하지 않는다. 이는 작은 표본에서 제품 동일성을 보조하는 보수 규칙이며 일반 매칭 정확도나 임상 효능 기준이 아니다.

## 추출 실패 최소 진단 — 2026-11-10

마지막 신규 URL은 수집 성공 뒤 추출 `request_failed`로 끝났으나 실제 원인은 미분류다. 추출 결과에 안전한 분류만 보존한다. 보고서 선택 `extraction_status: {code: string}`는 고정 allowlist `extracted`, `not_configured`, `budget_exhausted`, `timeout`, `authentication_failed`, `permission_denied`, `rate_limited`, `connection_failed`, `provider_error`, `invalid_response`, `incomplete`, `refused`, `request_failed`만 사용한다. 기존 보고서의 필드 부재는 호환한다. 예외문구·요청/응답 body·헤더·URL·키·토큰·자유형 provider detail은 저장/로그/응답에 넣지 않는다.

SDK typed exception과 응답 구조화 상태에 근거해 분류하며 알 수 없는 실패는 request_failed다. 모호한 결과를 성공 추출로 만들지 않는다. 화면 기존 표시 정보 추출 check에는 각 분류의 간단한 한국어 이유를 사용하고 score/공식판정 계약은 유지한다. 호출 재시도/모델/시간상한 변경 없이 누적 예산 예약·snapshot·fencing을 보존한다. 버전은 과거 실패 snapshot과 새 분류를 혼동하지 않게 관리한다.

### 확인된 timeout 후 최소 reasoning 조정

2026-11-10 신규 URL 실진단에서 `extraction_status.code=timeout`을 확인했다. 같은 GPT-5.6 Luna의 Responses parse 요청에 `reasoning={"effort":"low"}`를 명시한다. 모델·페이지 원문·스키마·4,000 출력한도·15초 외부/60초 시도/180초 활성·호출예산·grounding·매칭조건은 유지한다. collection snapshot 버전을 올려 기본 medium 실패 스냅샷을 재사용하지 않는다. 이 옵션은 속도 개선의 가설이며 관련 회귀와 실제 신규 URL에서 추출 결과·후보 모호성 보존을 확인하기 전 효과를 단정하지 않는다.

공식 근거: [GPT-5.6 Luna 모델](https://developers.openai.com/api/docs/models/gpt-5.6-luna)은 low를 지원하며 기본값 medium이다. [Reasoning 안내](https://developers.openai.com/api/docs/guides/reasoning)는 낮은 effort가 속도·토큰 사용을 줄이는 방향임을 설명한다. 정확도·완료시간의 보장은 아니다.

### 마지막 좁은 추출 실험

Low 적용 후 KGC1건은 추출 완료했으나 별도 ER Hana URL1건은 timeout이었다. 마지막 유한 수정 루프는 공식 지원되는 같은 GPT-5.6 Luna의 `reasoning={"effort":"none"}`와 collection snapshot5로 한정한다. 원문·스키마·4,000 출력한도·15초·grounding·매칭조건은 유지한다. 관련 작성자/독립 QA 뒤 ER Hana1회에서 검증하며, 또 실패하면 임의 내용 생략·분할호출·시간상한 확장 없이 미달과 필요한 사용자 선택을 명시한다.

## 사용자 승인: 번호 기반 등록 대조와 판매명 차이 — 2026-11-10

사용자는 확률 없이 구매 판단 단서를 제공하는 기준을 승인했다. 기존 번호 없는 엄격 조건은 유지한다. 새 확인 경로는 원문 신고번호와 제조사 일치, 완전한 번호 조회의 단일 공식 기록, 주요 기능성 원료 대조 충족, 비교 가능한 함량·제형의 모순 없음이 모두 필요하다. 판매명 차이를 숨기지 않으며 일반 부원료2개 일치만으로 이 경로를 확인하지 않는다.

- 공식 주요 원료는 `RAWMTRL_NM`의 독립 항목을 기준으로 모두 페이지에서 grounded 추출된 성분과 대조한다. `INDIV_RAWMTRL_NM`은 원료 표현 보조 출처이며 일반 부원료 `ETC_RAWMTRL_NM`은 주요 원료 충족을 대신하지 않는다. 공백·동등 상표기호(®/Ⓡ)만 정리하고 비타민D↔D3혼합제제 같은 동의어·전환이나 원료 변형 삭제를 추정하지 않는다. 주요 목록이 없거나 일부 대조가 부족하면 candidate다.
- 비교 가능한 함량은 같은 성분·숫자·단위·섭취 기준에서만 비교한다. 기준이 없거나 다르면 missing으로 표시하고 임의환산하지 않는다. 같은 기준에서 값이 다르면 conflict로 이 경로의 확인을 막는다. 제형은 페이지에서 직접 확인된 값만 대조하며 없는 값은 missing이고 추정하지 않는다. 확인하지 못한 함량·제형도 결과에 명시한다.
- `official_match`에 선택적 `name_difference: {page_name: string, official_name: string}`를 추가한다. 이 경로의 reasons code는 `registration_identity_with_name_difference`이고 state matched/check verified지만 제목·설명은 정확히 `공식 등록정보 대조 확인 — 판매명 차이 있음`이다. 이름 evidence의 conflict와 원문/공식 이름을 그대로 남겨 이름이 일치한 것처럼 표시하지 않는다. 확률·효능·점수는 만들지 않는다.
- 기존 product 원문·공식 원문 record·provenance를 보존하며 새로운 source의 값을 추출 입력에 역주입하지 않는다. collection/supplement snapshot 버전을 올려 이전 판정을 재사용하지 않는다. generic report JSON 계약이므로 DB migration은 요구하지 않는다.
- 이번 최소 변경에서는 모델 추출 스키마·제형 필드를 새로 요구하지 않는다. 기존 grounded 정보로 비교 가능한 제형이 없으면 missing으로 명시한다. 없는 제형·함량 기준을 추정하지 않는다.

소유권: Luna backend agents/**+관련tests, Luna frontend frontend/**(types/Report 포함), 리드 docs/README, root scripts/live/deploy. 작성자 완료 뒤 새 독립 Luna QA를 호출한다. 동일성 정책 범위를 초과한 수집·모델·시간·예산 변경은 없다.

### 실제 페이지의 필수 표 추출 지시 보완

새 경로 첫 신규 URL은 원재료 혼합제제만 추출하고 페이지의 영양·기능정보표 성분을 누락해 올바르게 candidate가 됐다. 같은 모델/none/스키마/원문/15초/예산을 유지하고 시스템 지시에 원재료목록과 영양·기능정보표의 성분명·함량·단위·섭취 기준을 각각 원문에서 추출하도록 명시한다. 원산지는 성분명/섭취 기준으로 쓰지 않고, 상표·기능성 등록코드는 보존하며 추정·환산은 금지한다. collection snapshot7로 이전 누락 추출을 재사용하지 않는다. 판정 기준을 낮추거나 공식값을 추출에 넣지 않으며 실제 재검증 전 효과를 주장하지 않는다.

### 명시된 제품정보 표 직접 읽기 — 세션 내 안정화

30초 모델 호출에서도 timeout이 발생해, 제품정보 표의 명시적인 값을 직접 읽는 경로를 먼저 수행한다. 표의 제품명·제조업소·품목제조신고번호·기능정보 원료가 모두 명시돼 있고 같은 제품으로 연결되는 경우에만 사용한다. 관련 제품·판매자·사업자 번호·숨긴 script/style/noscript/template를 섞지 않으며, 모호하면 기존 모델 추출 경로로 돌아간다. 다른 표를 연결할 때 단순 제품명 부분문자열로 변형 제품을 합치지 않는다. 원료의 상표·등록코드를 보존하고 제조업소 역할 라벨과 업체 값을 구분한다. 실제 HTML에서 읽은 문자열을 기존 원문 grounding으로 재확인하며 API 값을 넣거나 미기재 함량을 추정하지 않는다.

직접 읽기 성공은 `extraction_status.code=structured_page`로 명시하고 AI 추출 성공으로 표시하지 않는다. 이때 모델 호출·모델 호출 예산 예약은 0이며 실제 공식 API 대조는 기존 기준과 예산을 그대로 사용한다. 모델 키가 없어도 실제 표를 읽은 사실만 보고하며 모델 기능의 미설정을 성공으로 바꾸지 않는다. 광고 문구 전체·함량·제형을 읽지 못했다면 이를 한계로 표시한다. collection snapshot9가 이전 실패를 재사용하지 않게 한다.

### 추출 전용 시간 제한 분리 — 세션 내 마감 보완

실 URL에서 15초 timeout이 반복되고, 별도 실진단에서는 같은 원문에서 주요 원료 모두가 추출되는 변동성을 관찰했다. 사용자의 이번 세션 M1 마감 요청에 따라 구현 리드가 추출 호출의 기본 제한을 별도로 30초로 조정한다. `model_timeout_seconds`는 기본30·최대30초이며 `_extract`에만 사용한다. 수집·공식 API의 `external_timeout_seconds`는 최대15초를 유지한다. SDK 자동 재시도0, 누적 호출 예약, 전체180초·시도60초·총20회·역할6회·fencing은 그대로다. 호출 전에 선택한 시간을 예약하고 부족하면 실행하지 않는다. collection snapshot8로 과거 제한의 실패를 재사용하지 않는다. 이는 추출 대기 시간의 조정이며 매칭·grounding·모델·효능 판단 기준을 바꾸지 않는다. 실제 개선 효과는 별도 실 URL 결과와 전체 시도 이력으로 판단한다.

## 한정 M1 평가 하네스 — 2026-11-10

평가 게이트는 `docs/evaluation/m1-gate.md`다. root는20개 고정 manifest/라벨과 live 실행을 소유한다. 하네스 작성자는 `scripts/evaluate_m1.py`와 전용 테스트, 독립 QA는 별도 테스트/리뷰만 소유한다. 제품 agents/frontend/예산/매칭 코드는 수정하지 않는다.

Manifest 최소 객체는 `{version: string, frozen_at: string, sites: [{id: string, domain: string}], samples: [{id: string, site_id: string, url: string, labels?: object}]}`다. 정확20개·고유 sample id/URL·사이트3~5·선언된 site_id·공개HTTP(S)·frozen_at을 검증하고 전체 바이트 hash를 기록한다. labels는 판정 전용이며 page/model 입력으로 전달하지 않는다. optional `labels.identity`는 product_name/manufacturer/report_number별 `{status: "known"|"unknown"|"not_in_page", values?: string[]}`다. optional `labels.official_registration`은 `{status: "known"|"unknown", report_numbers?: string[]}`다. known 정답번호 목록에 없는 matched_record는 false_match, unknown은 unjudged다. 이 라벨은 원문과 독립 공식 근거에 기반해야 하며 빈 목록으로 미등록을 추정하지 않는다.

기본 실행은 collect-only, `--use-configured-keys` opt-in일 때만 모델/공식 연동한다. URL당 모델 요청은 최대1회이고 부분실행/재개에서도 completed sample ID를 다시 호출하지 않는다. 출력은 run id/manifest hash/code hash/시각/모드와 사이트별·전체 분모, 단계별 상태·지연·실제 요청 수, 보고서 및 제한을 보존한다. 설정 bool/예산 예약을 실제 호출 수로 표시하지 않는다. 예외 원문·키·인증 URL·토큰은 로그/출력에 넣지 않는다. 수집 실패도 원래20개 분모에 남긴다. invalid manifest는 외부 호출 전에 실패해야 한다.

Manifest 부가 metadata `cohort`(regression_seed/holdout_discovery), discovery_url, expected_display_name은 발견 경로/표본 식별에만 사용하며 모델에 전달하지 않는다. product_name 라벨은 report.product.name과 대조한다. URL host는 선언 domain과 같거나 dot 경계 subdomain이어야 한다. sample 시작 및 모델 invocation 전 상태를 durable checkpoint에 기록하고 재개 시 in_progress URL은 interrupted로 남겨 자동 재호출하지 않는다. 설정/예약 수와 실제 SDK parse 요청 시도 수·완료 수는 분리한다.

## 2026-11-11 최신 실행 제한

사용자 명시 지시로 M2는 보류·미진입이다. 현재 M1 한정 평가 마지막 guard QA·결과 기록만 마감하며 이전 M2 진입 계획은 실행 권한이 아니다.

## M2-A 승인 계약 — 2026-11-11

기준은 [승인 설계](superpowers/specs/2026-11-11-m2a-evidence-review-design.md)와 [구현계획](superpowers/plans/2026-11-11-m2a-evidence-review.md)이다. UI와 최종 필수 코드 수정은 독립 검토를 마쳤다. 사용자 A 선택으로 최종 실PG 전체 재검증·실행 반영·실연동은 다음 한도로 이관한다. 아래 계약은 완료 주장과 구분한다.

- POST `/api/analyses`의 선택 필드 `mode`는 `collection|evidence_review`다. 기본값은 `collection`이다. 기존 접수 응답과 게스트 토큰을 유지한다. GET은 mode를 추가 반환한다. 토큰 누락·오류는 기존처럼 404다.
- DB migration 0003은 기존 행의 mode를 collection으로 보존한다. 상태 enum, 보완 1회, 시도·활성 시간·도구 예산을 유지한다.
- evidence_review도 M1부터 실행한다. missing_fields가 있으면 needs_input이며 조사는 not_started다. 보완 후에도 부족하면 can_supplement=false다. missing_fields가 빈 배열일 때 조사를 시작한다. 공식 matched를 추가 조건으로 강제하지 않는다.
- 조사 report는 scope=evidence_review, score=null, verdict=hold다. M1 필드를 유지하고 원본을 collection_report에 둔다. research는 다섯 역할의 결과, 공개 출처, 선택 이유, 한계, 사용량을 담는다. 비회원 personal_fit은 not_applicable이며 모델 호출은 0이다. 원료 논문을 완제품 효능으로 확대하지 않는다.
- 출처의 text는 내부 snapshot 전용이다. 공개 report에는 넣지 않는다. discovery는 본문 근거로 인정하지 않는다. 인용은 출처 registry와 원문 포함 검사를 통과해야 한다.
- usage.total은 M1 수집을 포함한 누적 외부 요청 예약 수다. 복원 오류에서도 DB 총계를 보존한다. 역할별 귀속을 모르면 by_role:null, attribution:unavailable로 표시한다.
- 총 20회, 역할당 6회, 동시 전문 역할 3개, 재지시 총 2회·같은 역할 1회, 일시 오류 retry 전체 1회를 유지한다. 모델·HTTP 요청 전에 DB 예약과 snapshot 저장을 마친다. lease 상실 후 새 요청을 차단한다.
- 창 부족은 현재 유효 claim에서만 queued yield로 처리한다. 보고서·snapshot과 예산을 보존한다. 세 번째 시도 또는 활성 예산 마지막에는 completed 작업·partial 조사로 끝낸다. 완료 조사를 자동 재접수하는 API는 추가하지 않는다.
- 복원 시 `DB 예약 총계 == snapshot 총계 == M1 불변 baseline + owner 합`이어야 한다. 차이가 있거나 조사 시작 후 snapshot이 없으면 budget_state_mismatch로 외부 호출 없이 부분 종료한다. 불명확한 in-flight는 unknown_interrupted로 남기고 자동 재호출하지 않는다. M1 저장 후 첫 research checkpoint 전 중단도 보수적으로 M1을 보존하고 외부 호출 없이 부분 종료할 수 있다.
