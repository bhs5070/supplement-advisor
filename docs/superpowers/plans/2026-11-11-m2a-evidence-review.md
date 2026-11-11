# M2-A Evidence Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** URL 수집 보고서에 선택적 Supervisor/전문역할 근거 조사를 연결하고 실제 출처·한계·부분 결과를 저장/조회한다.

**Architecture:** 기존 M1 그래프는 유지하고 별도 research_graph를 Worker에서 연결한다. 공통 DTO/예산과 외부 도구는 분리하고 DB mode/원자 yield로 M1 호환·복구를 유지한다. 작성자와 task/final 검증자를 분리한다.

**Tech Stack:** 기존 Python3.11+, FastAPI, SQLAlchemy/PostgreSQL, Celery/Redis, HTTPX, LangGraph, OpenAI GPT-5.6 Luna, React/TypeScript/Vite. 새 SDK 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-11-11-m2a-evidence-review-design.md`. 사용자가 상세 설계 제시 뒤 “가자”로 설계와 계획 작성→EGM→TDD 진행을 승인했다. 이 계획의 개별 기술 명세를 이미 읽고 승인했다고 주장하지 않는다. 기존 승인 범위 안의 구현 결정과 검토 지적은 아래 기록한다.

## Global Constraints

- 활성180초·한 시도60초·최대3시도·240초lease, 총20회·역할당6회·동시전문3, Supervisor재지시총2/동일역할1을 보존한다.
- 모델·HTTP 실제 외부 시도는 호출 전에 원자 예약하고 SDK재시도0. 불명확한 in-flight는 crash 후 자동 재호출하지 않는다.
- M2-A scope=evidence_review, score=null, verdict=hold. 회원 개인적합성은not_applicable/모델0. M1 기본mode=collection과 과거 보고서를 보존한다.
- 키·토큰·인증URL·예외body를 출력하지 않는다. URL/문서/모델결과는 신뢰할 수 없는 데이터다. 기존 SSRF·fencing·보완1회·출처 구분을 유지한다.
- 리드Sol/구현·QA Luna/동시리드포함최대4. 별도 역할 소유 파일만 수정한다. 구현자는 하위 Agent를 만들지 않는다.
- 최초커밋전 전체미추적 작업공간을 보존한다. 이 실행은 원위치작업이며 기존파일 삭제·최초커밋·브랜치전환·자동commit/push/worktree생성을 하지 않는다. 검토 diff는 작업 전 바이트 사본과 후속 파일의 no-index diff로 만든다. 이 규칙은 현재 사용자 승인 범위의 기존 작업 보존을 위한 실행 적응이다.
- 외부 연동 결과와 모의/저장원문 검사를 구분한다. 모든 완료 조건은 실제 명령·코드hash·결과와 연결한다.

## Review Focus

1. 수집 완료 직후 crash/60초 창 종료에도 M1 보고서가 지워지지 않고 mode/예산/보완 상태가 유지됨(Task3).
2. 병렬역할의 snapshot/DB 예약 경쟁에도 총20·역할6/중복실행 제한이 깨지지 않음(Task2/3).
3. 자료 검색 성공이 본문 조회·제품 효과 확인으로 둔갑하지 않으며 존재하지 않는 출처/인용 거부(Task1/2).
4. 보완후 needs_input/can_supplement=false와 terminal partial에서 UI가 자동 새 접수를 발행하지 않음(Task3/4).
5. 오래된 Worker·잘못된 토큰·캐시 버전·부분 실패가 다른 사용자의 결과나 새 모델 호출을 만들지 않음(Task2/3/5).

## Shared interfaces

Task1은 `src/supplement_advisor/agents/research_types.py`를 만든다. Pydantic extra=forbid 모델: `ResearchSource`, `Finding`, `RoleResult`, `RoleAction`, `SupervisorDecision`, `ResearchResult`.

- `RoleId`: composition/claims/personal_fit/safety/official_quality. 도구는 search_official/search_literature/fetch_source/finish. 임의 역할/도구 이름 거부.
- `ResearchSource`: id,kind(official/research/discovery),title,url,retrieved_at,provider,document_id?,pmid?,doi?,published_at?,access_scope(discovery/abstract/document),excerpt,text. text는 내부전용 최대24000자, excerpt최대500자. 공개 변환에서 text 제거. url은 공개http(s)·인증정보없음, 공개 표시에서 쿼리/fragment 제거.
- `Finding`: statement(1000자),status(supported/contradicted/mixed/not_assessable),source_ids(최대10),quotes[{source_id,excerpt(500자)}],applicability(ingredient_only/product_label/product_applicable/unassessed). 원료 연구만으로 product_applicable을 허용하지 않는다. 근거가 필요한 사실에는 기존 source ID와 정규화한 원문에 포함되는 인용이 필요하다.
- `RoleResult`: role,status(completed/partial/insufficient_evidence/not_applicable/unavailable/failed),question,findings(최대10),missing_information,reasons. personal_fit은 비회원not_applicable로 deterministic 생성.
- `RoleAction`: action(tool중1),query(최대300자)?,source_id?,result(RoleResult)?. finish는result필수. fetch_source는registry의source_id만 가능.
- `SupervisorDecision`: action(dispatch/finish),assignments[{role,question}],reason. dispatch는1~3고유역할. 미선택역할 이유를 최종 결과에 남긴다.
- `ResearchResult`: status(completed/partial/unavailable),roles(5개역할을중복없이표시),sources(공개DTO),limitations,termination_reason,decisions(실행행동/역할/이유),usage(총·역할별시도/재지시).

외부 도구 모듈 `EvidenceTools(settings, reserve, *, owner="evidence", transport=None)`는 `async search_official(query:str)->list[ResearchSource]`, `async search_literature(query:str)->list[ResearchSource]`, `async fetch_source(source:ResearchSource)->ResearchSource`를 제공한다. `reserve`는 실제 모델/네트워크 요청 직전에 호출되는 `Callable[[str,float],bool]`이며 owner와timeout을 받아 거부 시 요청0. 도구의 owner는 생성 때 전문 역할 ID로 고정한다. 도구는 실패를안전코드로변환한 `ResearchToolError(code)`로 반환한다. HTTPX transport 주입은 테스트만 사용한다.

예약 연결은 하나다. graph의 `reserve(owner:str, timeout:float)->bool`은 로컬 owner6/전체20/deadline을 먼저 검사하고 기존 runtime의 `reserve_budget(seconds=0,tool_calls=1)`를 호출한다. DB 창 시간은 Worker에서 이미 예약했으므로 HTTP/모델 timeout을 DB 활성 시간에 다시 합산하지 않는다. DB가 수락하면 전체/owner 카운터를 증가시켜 snapshot과 in_flight를 동기 저장한 뒤 true를 반환한다. 저장 실패/lease 상실이면 외부 요청을 시작하지 않는다. 실패·재시도도 각각 동일 API로 1회씩 예약한다. callback이 없으면 테스트의 로컬 한도를 사용한다. Worker는 M1 처리 후 DB의 현재 `tool_calls_reserved`를 `runtime.initial_tool_calls`로 전달한다. 신규 조사 시 그 값을 불변 `collection_tool_calls`로 저장한다. 재개 시 DB 총계와 snapshot 총계가 정확히 같아야 하며 차이를 추정 보정하지 않는다. 도구 모듈이 자체적으로 재시도하지 않으며 graph가 일시 실패1회만 재시도한다.

정확한 순서는 다음과 같다. 중앙 graph가 구조화 assignment를 검사하고 owner를 composition/claims/safety/official_quality/supervisor 중 하나로 고정한다. personal_fit는 예약할 수 없다. EvidenceTools는 생성 때 받은 owner를 그대로 `reserve(owner, min(request_timeout,15))`에 전달하고 graph의 모델 요청은 같은 callback을 `reserve(owner,min(model_timeout,30))`로 사용한다. timeout은 유한 양수인지 검사하고 남은 monotonic 시간과 비교한다. 동기 callback은 await 없이 단일 event-loop에서 state 갱신/DB 예약/snapshot 저장까지 끝내며 role별 HTTP 예약도 모두 이 callback을 거친다. 외부에서 owner를 바꿀 수 있는 payload는 없고, source registry·결과 merge는 같은 중앙 lock 아래서 처리한다.

하나의 도구 행동이 HTTP3회를 쓰면 각각 요청 직전에 `reserve(owner,timeout)`를3번 호출하고 매번 counters/in_flight를 저장한다. 각 요청 사이에 다음 예약이 거부되면 외부 요청을 더 보내지 않고 안전한 tool_error를 반환한다. 논리 행동의 전체 결과를 중앙에서 합쳐 저장할 때에만 해당 in_flight를 지운다. DB 예약→snapshot 저장 사이 crash는 owner를 복원할 수 없는 예약 차이를 남긴다. 이런 경우 역할별 예산을 추정하지 않고 `budget_state_mismatch` partial로 외부 호출0 종료한다. 정상 복원은 `snapshot.counters.total == runtime.initial_tool_calls` 및 `snapshot.counters.total == snapshot.collection_tool_calls + sum(snapshot.counters.by_owner.values())`를 모두 만족해야 한다. 신규 snapshot이 없지만 M2 envelope가 이미 research 시작을 표시한 경우도 이 안전 종료를 사용한다. 이 규칙은 role6/total20 예약을 새로 주지 않는다.

Task2는 `async run_research_graph(collection:dict, settings, *, checkpoint=None, snapshot:dict|None=None, remaining_seconds:float|None=None)->dict`를 만든다. 반환은 `{report:dict,snapshot:dict,yielded:bool}`. Worker runtime settings는 기존 키/timeout·max_tool_calls와 `reserve_budget(seconds,tool_calls)->bool`, `save_snapshot(snapshot)->bool|None`를 제공한다. research code는 DB를 직접 열지 않는다.

여기서 checkpoint는 선택적인 동기 snapshot 저장 callback이며 주어지면 settings.save_snapshot 대신사용한다. native LangGraph checkpointer와동일하다고주장하지않는다. 제어는실제StateGraph의supervisor/dispatch/aggregate/report 노드와조건부edge로구성하고, 복구는아래fenced durable snapshot을이용한다. 원문과도구정보는시스템지시와분리하며한모델입력에총24000자이내/출력4000토큰/기존none reasoning을사용한다. 모델키없음/거부/불완전응답/invalid enum은가짜조사성공으로바꾸지않는다.

research snapshot의 고정 형식은 `{version:1,fingerprint:str,collection:dict,collection_tool_calls:int,phase:str,roles:dict[RoleId,dict],sources:list[dict],decisions:list[dict],counters:{total:int,by_owner:dict[str,int],redirect_total:int,redirect_by_role:dict[str,int]},in_flight:dict[str,dict],termination_reason:str|null}`이다. fingerprint는 원래collection의 product/ingredients/claims/official_match/sources를 정렬 JSON으로 SHA256한 값이다. counters.total은 M1 포함 누적 시도, by_owner는 새 조사 owner별 시도다. 역할 상태에는 question,status,pending_action,result,retry_used를 저장한다. 한 owner의 모델 또는 논리 도구 행동을 시작하기 전에 in_flight[owner]={kind,sequence,action}을 기록하며, 도구 내부 여러 HTTP 예약도 그 행동과 카운터를 함께 저장한다. 결과·출처·카운터가 중앙 merge/저장된 같은 snapshot에서만 표식을 제거한다. crash 시 표식이 남은 owner의 행동은 unknown_interrupted로 partial 종료하고 재호출하지 않는다. phase=report와 완성 report가 있으면 외부 호출0으로 반환한다. 병렬 작업은공통RLock의동기구간에서state변경/예약/저장을수행하고그안에서네트워크await를하지않는다.

복원 안전성은 fail-closed다. phase는supervisor/roles/report만 허용하고 필수 필드 부재·잘못된 타입·음수/비정수 카운터·알 수 없는 role/owner/phase·total<by_owner합은 `snapshot_invalid`로 분류해 외부 호출0의 partial 보고서와 기존collection을 반환한다. 비어 있지 않은 research snapshot의 version/fingerprint 불일치는 `snapshot_incompatible`로 같은 방식으로 종료한다. 바로 앞 문단의 “새 입력으로 시작”은 snapshot이 아예 없는 신규 조사에만 적용하며, 불일치한 기존 조사를 새 실행처럼 자동 재시작하지 않는다. 이 명확화는 역할별 과거 예산을 추정해 초기화하지 않기 위한 것이다. 완성phase의 report는 snapshot에직렬화해저장하며복원반환때도DTO와scope/score를검사한다.

일시 오류 retry는조사전체최대1회로보수적으로정한다. counters.retry_total 필수int(0..1)을추가해재개시보존하고어느owner가썼는지해당역할retry_used에표시한다. Supervisor재지시2회와별개이며모든retry도새외부예약을거친다. EvidenceTools의PubMed fallback은서로다른provider조회이며동일provider자동재시도는하지않는다. 직접API/SDK의숨은retry는0이다.

M2 공개 report는 기존 collection필드를 유지하고 scope=evidence_review로 바꾸며 `collection_report`에원래M1보고서, `research`에ResearchResult를둔다. score=null/verdict=hold. 미진입 M1 needs_input도 mode=evidence_review로조회되지만 report.scope는collection_only이며 `research`에not_started/reason을선택첨부할수있다. 전체 report JSON은길이제한된값만저장한다.

Task3은 `yield_analysis(session, analysis_id:str, *,claim_token:str,snapshot:dict,report:dict)->bool`를 repository에 추가한다. 현재running/유효claim/lease만조건update, statusqueued·claim/lease해제·snapshot/report저장·error/completed_at정리. attempt/active/tool/supplement/raw_file 보존. commit은호출자.

## Task 1: Typed evidence tools and grounded findings

**Files:** Create `src/supplement_advisor/agents/research_types.py`, `src/supplement_advisor/agents/evidence_tools.py`, `tests/test_evidence_tools.py`. Modify `src/supplement_advisor/collection.py`, `tests/test_collection.py`의선택callback경계만. 추가 허용: `tests/test_extraction_diagnosis_review.py`의 기존 snapshot 기대9→10 정정1건(리드가변경전graph동일hash/기존실패확인후작성자에게명시배정했다). config.py/collection_graph.py수정금지. 소유: evidence 작성자.

**Interfaces:** 위 Shared interfaces DTO/도구. EvidenceTools는고정API(Tavily/EuropePMC/PubMed)와기존safe HTMLcollector를 사용한다. 표준라이브러리XML parser 사용; 네트워크는HTTPX. 키는기존settings.tavily_api_key.

`collect_page(url, *,timeout=15,max_bytes=2000000,reserve_request:Callable[[],bool]|None=None)`로호환확장한다. 각hop의URL/DNS검증뒤실client.stream직전callback을호출하고false이면CollectionError("budget_exhausted",안전문구)로요청없이중단한다. 기본None의기존M1동작은유지한다. EvidenceTools의공식문서fetch는바깥에서별도1회예약하지않고이callback으로매HTTP를예약한다. 수집기를복제하지않는다. 새RED는2hop예약2회/두번째예약거부시두번째실요청0/None기존회귀다.

- [ ] RED: unknownrole/URLcredentials/초과길이거부, unknownsource/거짓quote거부, discovery를사실근거로거부, 같은PMID/DOI중복병합(서로충돌ID는비병합), source공개변환text제거 테스트를 먼저 작성하고 실패를 확인한다.
- [ ] RED: Tavily미설정·오류·0결과, PubMed/EuropePMC JSON/XML부분필드, 광고도메인제외, SSRF URL거부, 예약거부요청0, 도구의실HTTP요청개별예약을MockTransport로 검사한다. 결과최대5개/provider, body최대1MB, timeout최대15초. 공식discovery를안전본문조회후official/document로승격하고초록없는discovery의제목만으로근거판단을허용하지않는다. fullTextXML은실제제공된PMC형식ID로만요청하며PMID를PMCID로추정하지않는다. 실제외부호출없음.
- [ ] GREEN: `normalize_sources(sources:list[ResearchSource])->list[ResearchSource]`, `validate_findings(result:RoleResult,sources:list[ResearchSource],collection:dict)->RoleResult`를 research_types.py에구현한다. invalid판단은안전한insufficient_evidence와누락이유로낮추고출처를만들지않는다.
- [ ] GREEN: 도구3메서드 구현. search_official은Tavily basic/max_results5/include_answerfalse/include_raw_contentfalse/자동파라미터false, 공식도메인foodsafetykorea.go.kr,mfds.go.kr,ods.od.nih.gov만허용. result는discovery. 문헌은EuropePMC core JSON우선, PubMed 검색/esummary/efetch는별도요청계수·초록조회. fetch_source는논문ID기반고정API또는safe공식HTML만허용하며HTML본문확보후document로승격한다. 검색가용성실패는자료없음과구분한다. PubMed 요청은프로세스공유최대2/sec로제한하고429에서오류재시도를직접중첩하지않는다.
- [ ] CHECK: `.venv/bin/python -m pytest tests/test_evidence_tools.py -q --tb=short`, `.venv/bin/ruff check src/supplement_advisor/agents/research_types.py src/supplement_advisor/agents/evidence_tools.py tests/test_evidence_tools.py`. Expected: 전체pass. RED/GREEN출력을report에기록하고task독립review를받는다. commit은GlobalConstraints에따라하지않는다.

## Task 2: Bounded Supervisor and expert research graph

**Files:** Create agents/research_graph.py, tests/test_research_graph.py. Modify agents/__init__.py export only. 소유: runtime 작성자. Task1모듈은읽기만.

**Interfaces:** Shared interfaces run_research_graph. 그래프노드supervisor/dispatch/aggregate/report, 도구선택은RoleAction구조화응답. 실제AsyncOpenAI Responses parse/max_retries0/model기존값, 모델timeout<=30. 외부시도전에예약/스냅샷.

- [ ] RED: supervisor가claims/safety선택시그역할만호출, personal_fit0모델, enum밖역할/중복assignment거부, 역할다음도구선택후finish, 사용불가키를가짜성공으로만들지않는테스트를먼저작성·실패확인.
- [ ] RED: 총20/역할6, 동시최대3, 재지시총2/역할1, 오류retry1포함, 한도0추가요청, supervisor finish뒤미선택사유, 잘못된citation격하, 상충결과보존, 창부족yield, snapshot복원시완료노드재호출0/in-flight불명확재호출0/버전입력다르면비재사용을검사.
- [ ] GREEN: 역할별완료상태와immutable source registry를graph state에저장한다. 병렬역할은결과를중앙aggregate에서직렬merge한다. checkpoint는공통상태lock아래읽기/갱신/저장하고lease저장실패시모든후속호출중단. 총/역할카운터를호출직전동기예약한다. terminalreport는항상M1원본보존.
- [ ] GREEN: deadline은monotonic, 모델/외부timeout+2초저장여유가없으면호출하지않고yield한다. workersettings의시도남은시간을사용한다. supervisor는필요한역할만선택; 모든역할실행강제나고정요약으로대체하지않는다. retry는429/5xx/연결계열일시실패만1회. 사유코드는allowlist.
- [ ] CHECK: `.venv/bin/python -m pytest tests/test_research_graph.py tests/test_evidence_tools.py tests/test_agents.py tests/test_supplement_agents.py -q --tb=short`와담당파일Ruff. Expected: pass. source/controlmodel모의와실호출을구분한다. taskreview필수.

## Task 3: Durable mode, fenced yield and Worker/API integration

**Files:** Modify models.py, repository.py, schemas.py, main.py, tasks.py (src/supplement_advisor/), Create migrations/versions/0003_m2_evidence_mode.py, tests/test_research_backend.py. 소유: integration 작성자. 기존agents모듈수정금지.

**Interfaces:** Analysis.mode/AnalysisInput.mode defaultcollection Literal collection|evidence_review; GETmode반환. research snapshot envelope `{version:1,mode,collection_snapshot,collection_report,research_snapshot}`. 기존collection-onlysnapshot은기존경로유지. 호출할때 runtime에model_timeout_seconds와tavily_api_key를실제로전달.

M2의초기페이지수집도Task1의reserve_request를사용해각HTTP를DB에서예약한다. 기존Worker의수집전단일예약과중복차감하지않도록mode분기안에서그예약을callback으로이동한다. collection mode는기존경로를유지한다. fakecollector 테스트도명시callback을호출하게해가짜예약수치를증거로삼지않는다.

- [ ] RED: migration전기존행defaultcollection, 명시mode접수/조회/422, 404token, supplement mode유지/보완1회/재접수미발행, yield조건currentclaim·lease와모든budget보존을격리DB로먼저검사하고실패확인.
- [ ] RED: collectionmode는기존graph만, evidence mode는M1missing빈배열만research진입, 보완뒤부족needs_input/cansupplementfalse, 완료M1snapshot복원시수집/추출재실행0, 부분결과보존, gracefulyieldqueued·다음beat재발행,3시도/180초종료,staleclaim저장거부를모의검사.
- [ ] GREEN: migration에mode컬럼NOTNULL/serverdefaultcollection/checkconstraint를추가한다. downgrade는mode컬럼/constraint만제거하고기존데이터를삭제하지않는다. schema/main은기존input/GET/token계약을유지한다.
- [ ] GREEN: Worker는동일attempt예약/fencing을유지하고M2envelope의완료M1보고서를재사용한다. 새M1보고서/rawfile은research시작전에fenced저장한다. 남은window는시작이후monotonic차이로전달한다. yielded를받으면 먼저현재attempt_count>=3 또는 active_seconds_reserved+다음window>180인지검사한다. 마지막시도라면queue화하지않고저장부분을completed/partial로terminalfinish한다. 그외에만yield_analysis로원자queue화하고terminalfinish를호출하지않는다. M1처리후runtime.initial_tool_calls를실DB값으로갱신한다. 보완부족상태표는Spec대로다. APIhealthscope는유지하고capabilities에research설정가능여부만추가하며비밀은반환하지않는다.
- [ ] CHECK: `.venv/bin/python -m pytest tests/test_research_backend.py tests/test_api_worker.py tests/test_supplement_backend.py tests/test_repository.py -q --tb=short`. PG는전용TEST_DATABASE_URL로별도검사하며SQLitepass를PGpass라고부르지않는다. Ruff/taskreview필수.

## Task 4: Explicit research choice and honest report UI

**Files:** Modify `frontend/src/main.tsx`, `frontend/src/types.ts`, `frontend/src/Report.tsx`, `frontend/src/style.css`; Create `frontend/src/ResearchReport.tsx`, `frontend/e2e/research.spec.ts`. 실제 frontend/playwright.config.ts의 testDir=./e2e를 리드가 확인했다. 소유: frontend 작성자. backend수정금지.

**Interfaces:** 명시선택한mode만POSTbody에추가한다. 기존type에EvidenceReport union을추가하고ResearchReport는collection_report/research를소비한다. 기존Report는collection전용으로재사용한다.

- [ ] RED: APIfixture로defaultcollection/body, 명시research/body, scope분기,5역할/개인미평가,partial/출처/점수없음,needs_input/can_supplementfalse,terminalpartial에서POST자동재발행0을브라우저테스트로실패확인한다.
- [ ] GREEN: 기존스타일과UI UX Pro Max대상한정검색을사용한다. 선택문구는“공식 자료·논문 근거도 조사하기”, 설명은“조사한 범위와 출처를 보여줍니다. 점수·구매 추천은 하지 않습니다.”로한다. sourceLink는http(s)만허용하고Reacttextescaping을유지한다. 역할이유·조회범위/시점·원료와완제품적용을구분한다.
- [ ] CHECK: `npm run test:e2e`의전용research desktop/mobile시나리오와`npm run build`. 실제렌더링/화면을확인하며fixture검사를liveAPI로부르지않는다. 독립UIreview를받는다.

## Task 5: Independent system verification and bounded live evidence

**Files:** Create `tests/test_m2_review.py`, `scripts/verify_research_live.py`, `docs/reviews/m2a-review.md`; Update `docs/tasks.md`, `docs/handoff.md`, `docs/contracts.md`, `docs/verification.md`, `README.md`. test/review는독립QA,verify script는리드또는전용writer,기록은리드가맡는다. 소스수정은해당writer에게돌린다.

**Interfaces:** live verifier는기존intake/get/token API만사용한다. URL과예상assertion을분리하고token/keys/예외body를저장하지않는다. 새유료URLrun은기본off/명시opt-in/원칙1건이다. 재시도로원래실패를지우지않는다.

- [ ] 독립QA가계약/품질/보안/복구의구체지적을기록한다. 중요/필수는writer가수정하고영향범위를재검증한다. 미해결중요사항을pass로처리하지않는다.
- [ ] 실PGmigration/경쟁예약/yield/staleclaim,관련pytest/Ruff,frontendbuild/Chromium을확인한다. 파괴적DBfixture는기존개발데이터와분리하며데이터볼륨을삭제하지않는다.
- [ ] 필수검증후로컬Compose를재build하고host/API/worker sourcehash·ready·migration을대조한다.
- [ ] 새URL1건으로collection→Supervisor실선택→자료조회→조사보고서→PG저장→token조회/무token404를검증하고실API/모델호출수·partial·미평가를기록한다. 실패는그대로보존한다.
- [ ] 최종review에서전체새변경을확인하고미검증·외부의존·남은작업을명시한다. 제품점수/추천완료와혼동하지않는다. 기존branch/작업을보존하고자동commit/push하지않는다.

## Self-review and current execution

Spec각장은Task1(근거/자료),2(역할/한도/snapshot),3(API/DB/보완/복구),4(UI),5(실증)로다룬다. 공유DTO는Task1에서먼저고정하고runtime→integration→UI가소비한다. ReviewFocus5개는담당task의RED사례에배정했다. mode생략시기존동작은Task3/4에서고정한다.

EGM대상은이plan전체와Spec이며implementation-readiness/codebase-details/style3persona를새컨텍스트로직접dispatch한다. 모두read-only다. 수정은중요도별로기록하고승인설계안의명확화는리드가판단하며설계방향변경은사용자에게확인한다. EGM전체5단계완료를주장하지않는다. 표준반복을단축하면완료/수렴을가장하지않고한정검토로명시한다.
