# 개발 루프 작업판

## 최신 마감 범위 — 주간 한도에 따른 A 선택

사용자는 필수 두 건의 수정·관련 테스트·독립 재검토·인계 기록까지만 진행하기로 선택했다. 일반 원료의 완제품 적용 제한과 초기 M2 HTTP 요청의 durable in-flight 기록을 수정했고, 추가 카운터 회귀까지 독립 재검토에서 ADDRESSED / scoped quality Approved로 마감했다. 실서비스 반영과 실제 URL 검증은 이번 범위에서 제외하고 다음 한도로 이관한다. 수정 후 지정90 passed/5 PostgreSQL 조건 skips, 이후 카운터 정정 대상1 passed와 Ruff 통과다. 마지막 수정본의 전체 실PG 검사는 아직 실행하지 않았다. 완료 증거는 작업 원장 `work/verification/m2a/progress.md`와 [최종 검토](reviews/m2a-review.md)에 추가한다.

수정 전 전체 검증은 실PG342 passed/4 skipped, Chromium fixture26 passed/22 filtered skips다. 이 결과를 수정 후 결과로 재사용하지 않는다. 실행 중인 서비스는 M1이며 공개 DB의 마지막 관찰값은 migration0002/분석19건이다. 준비한 Docker 이미지는 최종 수정 전 candidate이므로 다음 실제 반영 전에 **재빌드가 필요하다**.

## 이전 진행 기록

## 최신 사용자 지시 — M2 착수

최신 진행: 승인된 M2-A의 Task1 근거 도구, Task2 조사 그래프, Task3 DB·Worker·API, Task4 화면 연결은 각 작업의 독립 검토·필수 수정·재검토를 마쳤다. 모델 출력 schema의 역할·도구 enum 전달 누락도 보완하고 독립 검토를 통과했다. 현재 Task5 독립 시스템 검증을 진행한다. 그다음 Task5 독립 시스템 검증, 최종 전체 회귀, 로컬 실행 반영과 실제 URL 한 건 검증을 수행한다. 점수·구매 추천은 후속이다. 새 모델·자료 API 호출과 M2 배포는 아직 수행하지 않았다.

작업 원장은 `work/verification/m2a/progress.md`, 기준은 [M2-A 구현계획](superpowers/plans/2026-11-11-m2a-evidence-review.md)이다. 실PG 포함 319 passed/3 skipped는 Task3 마지막 보완 전 소스의 증거이며, 최종 수정 후 다시 확인한다. 화면은 fix1 전체 fixture E2E 25 passed/21 filtered skips, fix2 영향 3 passed/3 filtered skips와 빌드를 통과했다.

### 이전 착수 기록 — 상세 설계 승인 전

사용자가 Skill 설치 이후 **“M2 시작하자”**라고 명시해 이전 보류를 해제했고 **“A 가자”**로 조사 흐름 먼저 구현하는 순서를 선택했다. Luna 읽기 전용 연결점 조사와 기존 모의 회귀75개를 마쳤다. [M2-A 설계 초안](superpowers/specs/2026-11-11-m2a-evidence-review-design.md)을 작성하고 별도 Luna builder check의 질문3개를 명확히 했으며 재확인에서 중요한 미해결이 없다는 보고를 받았다. 상세 설계 사용자 승인 전이다. EGM 전체 검토·제품 기능 구현·배포·서비스 외부 모델/API 실행은 아직 수행하지 않았다. [M2 착수 기록](m2-kickoff.md)을 따른다. 아래 M2 미진입 지시는 당시 이력이다.

## 이전 보류 지시 — 2026-11-11

**M2는 사용자 지시로 보류하며 진입하지 않는다.** M1 한정 평가의 마지막 identity guard 독립9개 회귀·Ruff·diff·기록 마감까지 완료했다. 배정 범위의 필수 미해결 사항은 없으며 다음 작업은 실행하지 않는다. 기술적으로 다음 단계의 조건이 충족돼도 착수 승인이 아니다. 아래 M2 계획·진입 언급은 이전 합의/이력이며 새 설계·구현을 실행하지 않는다.

## 최신 판정 — M1 기본 기능 마감 (2026-11-10)

URL-only 실제 표 수집·주요 원료/공식 등록 대조·DB 저장·권한 조회의 독립 판매 페이지1건과 기존1회 추가 입력 경로를 확인했다. 관련 독립93회귀 및 실제 Chromium의 관련2개·build·시각 검증, 실행본 동일성 검증을 마쳤다. 세부 완료 범위와 실패 이력은 [M1 마감](m1-closeout.md)이다. 자동 추출의 폭넓은 품질 확보·전체 평가·회원·이미지는 완료로 세지 않는다. 아래 중간 상태는 이력이다.

## M1: 비회원 제품 조사 접수·수집

상태: 핵심 수직 기능 구현 및 실제 Compose 경로 1차 검증 완료. 독립 리뷰 필수 수정 5건과 관련/독립 재검증을 마쳤으며 Desktop 최종 작업공간에서도 재빌드·실제 접수·조회·복구 검증을 통과했다. 전체 제품 평가·회원 개인화 완료를 뜻하지 않는다.

| 작업 | 담당 역할 | 소유 경로 | 현재 증거/완료 기준 |
|---|---|---|---|
| DB·원자적 점유 | database | models/database/repository/migrations | SQLite + 실제 PostgreSQL 합계 29 passed, SQLite에서 PG 전용 검사 1 skipped. claim fencing·누적 예산·snapshot 구현 |
| 공개 URL 안전 수집 | collection | collection.py | 30 모의 검사 통과. 실제 example.com 수집 성공 |
| LangGraph 수집 보고서 | agent-runtime | agents/ | 16 모의 검사 통과. 외부키 미설정은 unavailable, 점수 없음. R3 수정 및 full 숫자/단위 grounding 검사 통과 |
| API·작업 통합 | api/infrastructure | main/tasks/config/schemas/celery/storage | 6 모의 검사 통과, 실제 접수→Worker→저장→조회 성공. R1/R2/R4 수정·재검증 통과 |
| 화면 | frontend | frontend/ | URL·진행·보고서·오류·조회 재시도 구현. 독립 소스검토 필수 지적 없음, TypeScript/Vite build·실제 HTTP/API proxy 통과. 브라우저 시각 확인은 host 불가로 미검증 |
| 개발 환경 | infrastructure | Docker/Compose/scripts | DB/Redis healthy, migrate/API/worker/beat 실행. Desktop 경로 최종 재빌드·접수·조회·복구 검사 통과 |
| 개발 모델 기본값 | lead | .codex/start-codex/AGENTS | Sol 리드·Luna 서브에이전트 기본값 반영, bash syntax/check 통과 |
| 독립 검증 | independent QA | tests/test_review_regressions.py, docs/reviews/m1-review.md | 작성자 분리. R1 시간예약·hard limit, R2 오류토큰404, R3 함량부분문자열, R4 async API blocking, R5 IPv6 site-local 재현; 수정 후 독립 5 passed |

## 추가 정보 선택 전 M1 종료 검토 — 2026-11-09 (당시 판정)

이 표는 추가 정보 입력을 M1에 포함하기 전의 판정이다. 당시 상태는 **핵심 구현·기존 실연동 검증 완료, 사용자 요청 추가 검증 진행 중**이었다. 아래 유한한 확인을 마친 후 결과와 미검증을 기록해 M1 종료 가능 여부를 판단한다. 검사 실행 완료와 매칭 품질이 충분하다는 판정은 구분하며, 이 당시에는 국내 독립 positive가 확보되지 않아 M1 전체 완료 판정을 보류했다. 이후 사용자가 선택한 확장 범위의 최신 완료 기준은 아래 추가 입력 항목을 따른다. 표본이 작거나 수집 한계가 있으면 그대로 기록하며 성공 사례를 만들기 위해 전체 평가 기능이나 수집 기술을 확장하지 않는다.

| 종료 항목 | 판정에 필요한 증거 | 상태 |
|---|---|---|
| 비회원 수직 경로·안전·복구 | 실제 DB/Redis/Celery/외부 추출/저장·권한 조회, 실제 prefork kill·hard-timeout 후 lease 복구, 독립 회귀 | 완료: 기존 검증 기록 참조 |
| 국내 제품 식별·공식 대조 추가 확인 | 서로 다른 국내 제품 3개·최소 2개 제조사 대상으로 독립 판매/제조사 원문을 관찰하고 추출값·공식값·정확한 분모를 비교. 독립 positive 미확보 시 검사 실행만 완료로 기록하고 품질 충분 판정은 보류. 수집 실패·이미지 전용·정보 부족은 별도 기록. 통제 negative와 독립 positive를 구분 | 검사 실행 확보: 3시도·2수집·실모델2완료·독립 positive 0. 품질 충분 판정 보류. 독립 QA 7+Agent19 passed/Ruff 통과 |
| 화면 행동 자동 검증 | 사용자 선택 도구로 접수·상태·결과·오류·토큰·복구·안전 표시를 검사하고 실제 브라우저 확인 여부를 명시 | 완료: 전용 5174 Chromium 9 passed/9 project skip, build·독립 QA·정상 화면 확인 통과 |
| 작성자와 분리한 검증·종료 기록 | 추가 하네스와 변경 코드에 독립 QA 및 Clean Code 리뷰, 필수 지적 해결 또는 실제 외부 blocker 명시 | 완료: 추가 검증 1차 UI 필수 2건 해소. 국내/화면 독립 리뷰 기록 |

국내 표본의 통과율은 해당 표본·측정 단계의 분모만으로 보고한다. 공식 record에서 만든 통제 입력은 실판매페이지에서 독립 확인한 일치 사례 수에 포함하지 않는다. 제품 등록 일치가 효과·함량·안전성을 증명하지 않으며, 전체 5개 전문 Agent 평가·점수·회원 개인화는 M2 이후 범위다.

## 루프 기록

1. 구현·관련 검사: DB/수집/Agent/API 모의 및 실제 PostgreSQL 검사, Docker 실연동 example.com 경로 통과.
2. 독립 검증: 필수 R1–R4 발견. 독립 회귀 4개 실패로 R2/R3/R4 재현, R1은 시간한도 구성 교차검토. 담당 구현자가 R1–R5를 수정했다. 관련 검사 64 passed/Ruff 통과, 별도 Luna 독립 QA 5 passed 및 실제 Celery hard60/soft59 확인.
3. 최종 경로: 원본 안정화 뒤 `/Users/hyeonseokbae/Desktop/ad_fact_check`로 복사하고 Compose 재빌드·실행·복구 검사.

자동 검사 원문은 `work/verification/`에 보관하며 버전 관리에서 제외한다. 정확한 최종 명령·결과·미검증은 `docs/verification.md`에 기록한다. 기본 수정 루프는 3회이며 미해결과 외부 의존을 완료로 바꾸지 않는다.

2026-11-09 잔여 검증 재개: 실제품 페이지 검사 도구(기본 무키, 외부 연동 명시 opt-in)와 별도 Compose prefork 장애 검증 하네스를 추가했다. 제품 흐름에 테스트 후킹을 추가하지 않았다. 최초 무키 샘플은 Solgar 수집 성공/NOW HTTP 실패이며 그 단계의 모델 추출·국내 공식 매칭 품질은 미평가였다. 새 하네스의 독립 소스 리뷰는 필수 지적 없이 9 passed, integration 1 deselected였다. 실제 프로세스 kill·hard-timeout 결과와 외부 인증 성공은 `docs/verification.md`에서 별도로 확인한다. 실행 중인 검증을 완료로 세지 않는다.

추가 실행 완료: 별도 실제 prefork kill/hard-timeout 시나리오 둘 다 기본 240초 lease 자연 만료 후 attempt 2/예약60초/호출2회/이전 claim 거부를 확인했다. 실제 OpenAI 가상 표시 1건과 공개 Solgar 제품 1건 추출, I0030 실응답 파싱, 공개 제품 API→Worker→저장·권한 조회 경로도 확인했다. 공식 동일성은 unverified·정보 부족은 needs_input으로 보존했다. 국내 실제 positive match, 폭넓은 품질 표본, 브라우저 클릭 검증은 남는다. 전체 5개 전문 Agent 평가·개인화·점수 기능은 계속 후속 마일스톤이다.

실API 통제 양성 검사에서 전체 이름 검색 누락을 발견해 신고번호 우선 조회로 최소 수정했다. 공식 record 유래 입력의 실제 양성 verified/제조사 오류 음성 unverified를 확인했고, 별도 QA Agent+회귀 24 passed/Ruff 통과였다. 국내 판매 페이지의 독립적인 positive match 품질 검사는 계속 남는다.

## 후속 마일스톤

- M2: 공식 자료·논문 검색, 5개 전문 Agent 실제 조사 루프와 Supervisor 선택·재조사·평가.
- M3: Clerk 회원·프로필·건강검진·영양소 안내와 이미지 입력. 수동 성분·한 번의 추가 입력 묶음은 2026-11-09 사용자 선택으로 M1에 앞당겼다.
- M4: R2·LangSmith 실연동, kind 장애·업데이트·처리량 실험.
- 별도 비교: Luna 업그레이드, CLOVA OCR, pgvector RAG 챗봇.


## 사용자 선택: 추가 정보 입력을 M1으로 앞당김 — 2026-11-09

국내 원문 2건에서 제품명·제조사는 추출했지만 신고번호를 확보하지 못해 공식 일치를 확정하지 못했다. 사용자는 필요한 정보를 한 묶음으로 보완하는 기능을 M1에 포함하기로 선택했다. 범위와 HTTP/모듈 계약은 `docs/contracts.md`의 추가 입력 항목을 따른다.

완료 기준: 권한 있는 needs_input 분석만 원자적으로 1회 입력 → 누적 예산/시도를 보존한 queued/beat 복구 → 원문·사용자 출처를 구분한 공식 재대조 → 토큰 조회·화면 보고서. 이미지·회원·전체 평가·추천은 제외한다. 관련 검사와 실제 브라우저 mock 검사, 작성자와 분리한 QA/Clean Code 필수 수정 해결 후 종료 가능 여부를 판단한다. 국내 자동 매칭 positive 0의 과거 결과는 보존하며 사용자 보완 후 대조 성공과 구분한다.


추가 입력 독립 QA 1차: 예산 소진 시 이전 보고서 유실, 선택 성분 공백 값이 null로 정규화되지 않는 필수 결함 2건을 재현했다. `docs/reviews/m1-supplement-review.md`와 독립 회귀 테스트에 기록했고 담당 작성자가 수정 중이다. Frontend·실제 통합은 아직 완료로 세지 않는다.


### 최신 M1 판정 기준

사용자가 선택한 확장 범위에서는 권한 있는 1회 추가 입력 → 누적 예산·시도 보존 → 실제 공식 재대조 → 토큰 조회·화면 출처 표시와 독립 QA를 완료 기준으로 삼는다. 국내 자동 추출의 독립 positive 0건이라는 한계는 별도로 유지한다. 공식 record 유래 통제 수동 입력의 성공을 자동 매칭 성능으로 바꾸지 않는다. 새 경로의 실통합·독립 QA 결과가 확정되기 전에는 완료를 선언하지 않는다.


### 추가 입력 구현 최종 실행 상태

작성자 분리 독립 QA 필수 4건을 해결했고 최종 관련 검사38 passed/18 PostgreSQL skips, Ruff, Chromium15 passed/13 viewport skips, production build와 desktop/mobile 시각 확인을 마쳤다. 실제 통제 needs_input → 권한 있는 1회 보완202 → Redis/Celery/I0030 verified → 토큰 조회 completed를 확인했다. 예산·시도 보존, 잘못된 토큰404·중복409·사용자 출처·null 성분 보존도 통과했다. 새 합의 범위의 **추가 입력 경로 구현·실행 검증은 완료**했으며 최종 evidence 독립 대조도 통과했다. 실행 서비스 DB/broker readiness, migration0002 및 API/Worker/Frontend 호스트·실행본 hash 일치까지 확인했다. 이번 구현·검증 루프는 완료했다. 국내 자동 매칭의 독립 positive0은 별도 한계로 남고 전체 제품 평가·회원·이미지는 완료 범위가 아니다.


최종 evidence: `work/verification/2026-11-09-supplement-live.json`, `2026-11-09-supplement-deployment.json`, `2026-11-09-supplement-source.sha256`. 독립 리뷰와 stdout/stderr 경로는 `docs/verification.md`에 있다. 최신 완료 판정은 사용자 합의의 추가 입력 경로에 적용되며 과거 자동 국내 표본의 품질 한계와 후속 마일스톤을 바꾸지 않는다.

## 재개: URL 자동 공식 매칭 — 2026-11-09

상태: 사용자 추천1 선택, 구현 중. 추가 입력 성공은 자동 목표의 완료가 아니다. 최신 공유 계약은 contracts의 자동 공식 후보 대조 확장이다.

| 작업 | 소유 | 완료 조건 |
|---|---|---|
| 계약·통합·판정 기록 | 개발리드 | 자동 확인/후보/미확인의 규칙·출처와 실제 결과·분모를 연결 |
| 공식 후보·다중근거 대조 | backend Luna | bounded 검색·metadata 보존·grounded 추가근거·모순/모호성 보수 판정·예산/snapshot 회귀 |
| 결과 UI | frontend Luna | 공식 번호 분리, 확인/후보/미확인과 증거·검색한계 표시, 기존1회 fallback, Chromium 계약/desktop/mobile |
| 독립 QA | 새 Luna | 작성자 분리 기능·근거품질·예산복구·보안·Clean Code, 필수지적 기본3회 수정 |
| 실제 검증·실행 반영 | root 지원 | 독립 cached 원문추출과 실제 I0030 후보 대조부터 수행. mock와 실API를 구분하고 필요하면 최종 URL 전체1회 |

종료 기준은 기존 국내 독립 원문 2건과 공식 실API 후보를 새 규칙으로 대조해 자동 결과·왜 그런지·한계를 설명할 수 있고, 에브리타임샷과 샷스트롱을 혼동하지 않으며, 자동 성공은 원문에서 독립 확보한 근거로만 입증하는 것이다. positive가 나오지 않으면 자동 목표 달성으로 선언하지 않는다. 관련 검사 통과만으로 완료 판정하지 않는다. 실제 자동 positive가 확보돼도 작은 표본의 일반 성능을 주장하지 않는다. 마지막 실행 반영 및 코드/실행본 일치를 확인한다.

### 자동 개선 실API 중간 종료 판정

cached 독립 원문 2건/원래 3시도 재대조에서 matched0, candidate1, unverified1(기존 수집실패1)이다. 에브리타임샷의 이름·제조사·부원료가 일치하는 서로 다른 공식 신고 2건이 있어 단일성 확인을 보류했다. 후보 검색·근거 표시의 개선은 구현했으나 **원래 자동 확정 목표는 아직 미달**이다. 사용자의 남은 실행 한도 내 종료 요청에 따라 추가 범위 확장은 멈추고 현재 필수 오류·독립 재검증·최종 배포 및 신규 URL 1회 증거만 닫는다.

최종 신규 URL-only 1회는 수집 verified 뒤 모델 request_failed로 needs_input이며 공식 조회까지 이르지 못했다(`2026-11-09-automatic-matching-url.json`). 현재 안전한 후보 대조 구현은 실행 반영했으나 자동 positive 0의 목표 미달을 유지한다. 사용자 실행 한도 내 종료 요청에 따라 추가 범위·모델 호출 없이 이번 구현/검증 루프를 종료한다. 이는 전체 M1 자동 목표 완료 판정이 아니다.

## 2026-11-10 재개: 모델 추출 실패 원인 확인

사용자는 이어서 진행을 명시했다. 새 범위 확장 없이 마지막 URL의 추출 request_failed 원인을 안전한 typed failure code로 구분한다. 새 Luna 작성자는 agents/**+관련 tests만, 새 독립 Luna QA는 분리한 tests/review만 소유한다. 리드는 docs/contracts/tasks, root는 live 진단/실행 반영/manifest를 담당한다. 작성자 관련 회귀→독립 필수 검증→제한된 실진단→증명된 필수 수정만 수행한다. 기존 15초 외부/60초시도/180초활성/총20·역할6회·snapshot/fencing과 매칭 보수조건은 유지한다. 2개 공식 신고가 모호한 결과는 candidate이며 자동 positive로 바꾸지 않는다.

후속 유한 검증: typed 진단의 신규 URL timeout 확인 뒤 reasoning low 명시·collection snapshot4만 최소 수정한다. 작성자 관련63 pass/Ruff/diff 통과 후 새 독립 재검증과 root 실URL을 실행한다. 기존3제품 표본 분모는 고정한다. root가 별도로 관찰한 ER Hana 판매사 페이지(원문에 제품명·제조사·신고번호 표시)는 추가 독립 편의표본1건이며 이전 표본의 성공률에 합치지 않는다. 표본 추가는 수집한 원문 identity를 그대로 추출/대조하며 공식 API값을 추출 입력에 넣지 않는다. 추가 실검증 결과가 나오기 전 positive로 세지 않는다.

최종 none ER Hana는 추출·번호 공식 조회를 완료했으나 판매명과 등록명이 달라 candidate다. 자동확정0은 유지한다. 번호·제조사·추가성분 일치와 이름 차이를 어떻게 다룰지 root가 사용자에게 규칙 선택을 요청했으며 응답 전 dependent 매칭 코드는 변경하지 않는다. 현재 none/v5의 안전한 실행본 manifest와 실증거 read-only 독립 대조만 마무리한다.

현재 none/v5 실행본의 최종 runtime/manifest는 `2026-11-10-m1-deployment.json` passed와 `2026-11-10-m1-source.sha256`으로 닫았다(API/worker/host·frontend 코드동일성, DB/broker readiness, migration0002). 실증거 독립 읽기와 관련73개 회귀·Ruff·diff를 통과했다. 이 단계는 안전한 실행·진단·후보 경로 종료이며 자동확정목표0을 완료로 바꾸지 않는다. 의미있는 이름 차이 처리 정책은 사용자 응답 전 변경하지 않는다.

## 사용자 승인 실행: 번호·제조사·주요 원료 대조와 이름 차이 표시

사용자는 확률 없이 다듬은 추천 기준을 승인했다. 새 경로는 계약 말미를 따른다. 완료 조건은 ①backend의 번호/제조사/주요기능원료/비교가능모순 게이트 및 원문보존 ②frontend의 판매명차이 명시·근거/누락표시 ③작성자와 분리한 필수QA ④기존 ER Hana 독립 artifact로 안전한 사전대조 후 root 신규 URL-only1회·실행본 manifest 검증이다. 일반 부원료만으로 성공시키거나 기존 번호 없는 조건을 낮추지 않는다. 실제 결과 전 자동positive를 선언하지 않는다.

## 2026-11-10 새 선택: 고정20개 평가 후 M2

M1 품질은1~2일 상한으로 제한한다. root는5사이트 고정URL20개 manifest/독립라벨과 raw live 실행, Sol 리드는 평가게이트/계약/기록, Luna 작성자는 evaluate_m1.py/전용tests, 새 독립 Luna QA는 검증/리뷰를 맡는다. 무모델 수집부터 시작해 manifest freeze와 라벨·정확분모를 보존한 bounded 실측을 수행한다. 모든URL 모델최대1회, unknown은unjudged, 실패표본교체금지, 실제콜계수와지연측정. 치명오류만수정하고지원범위를명시해M2진입을판정한다. 결과를미리성공으로가정하지않는다. 세부게이트는 evaluation/m1-gate.md다.

Stage1 고정 baseline은20개/HTML원문16개/SSG HTTP오류4개, 모델15요청·15완료, 직접 구조화 추출1, 공식26요청으로 종료했다. 원본 결과와 라벨은 바꾸지 않는다. 사후 matched2건은 er-15(원래known)와 gs-daypack(원래unknown)이며 별도 독립 판정을 진행한다. 공식unknown을사후gold로덮지않는다.

M2 전 마지막 필수 수정은 identity guard2개로 제한한다: 상세페이지참조 같은 placeholder를 제품명으로 보이지 않게 하고, 제조 역할과 같은 회사의 명시 결합 근거가 없는 ML footer회사값은 제조사None으로 보류한다. 기존 직접표 parser의 검증된 역할범위는 보존하며 인접한 제조단어 차용·전면사이트확장은 하지 않는다. 저장원문 기반 오프라인 회귀·독립 QA·새 소스 hash를 남기고 원baseline을 재실행하지 않는다.

## M2 진입 뒤 구체 다음 작업(아직 구현 승인 범위 아님)

M1 최종 guard·독립 QA·배포/구조화 URL 회귀가 끝나면 고정 평가 게이트를 닫고 M2 착수 상태로 옮긴다. 이번 sprint에서 M2 신규 제품 설계나 전문 Agent 기능을 임의 구현하지 않는다.

다음 작업은 현재 검증된 identity/공식 record/성분·광고 문구와 provenance를 입력으로 한 M2 첫 조사 경로의 범위를 비교표로 정하는 것이다. 비교할 최소 대안은 공식 기능성 표시와 광고 문구의 대조를 먼저 구현하는 경로, 문헌 근거 조사까지 함께 구현하는 경로다. 각 경로의 조사 범위·정보 부족 처리·호출/시간 예산·실제 출처 검증·종료 기준을 명시하고 사용자가 선택한 뒤 계약·과제·독립 QA 표본을 확정한다. 개인 적합성·점수·5역할 전체 평가 완료를 전제하지 않는다. 기존 M1 고정20개 원본은 회귀 기준으로 보존한다.

M2의 기존 합의인 Supervisor와 제품 전문 역할5개 구성은 유지한다. 위 비교는 그 구성을 폐기/축소하는 선택이 아니라 첫 구현 슬라이스와 아직 미정인 근거 판정 기준을 정하는 절차다. 전체5역할 완성과 첫 슬라이스 검증을 구분한다.
