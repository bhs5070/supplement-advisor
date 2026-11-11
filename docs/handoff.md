# Codex CLI 구현 인계

## GitHub 백업

사용자의 저장소 생성·push 요청에 따라 최초 커밋과 비공개 원격 저장소 `bhs5070/supplement-advisor`를 준비한다. 아래의 “최초 커밋 없음”과 원본 바이트 비교 설명은 M2 구현·검증 당시 이력이다. 다음 작업은 실제 Git 상태와 원격을 먼저 확인한다. 소스 실행 설정과 데이터는 이 백업 작업으로 변경하지 않는다. `.env`, 원문·실행 산출물, 외부 Skill 설치 사본은 제외하며 설치 목록은 보존한다.

## 최신 마감 범위 — 주간 한도에 따른 A 선택

사용자는 필수 두 건의 수정·관련 테스트·독립 재검토·인계 기록까지만 진행하기로 선택했다. 일반 원료의 완제품 적용 제한과 초기 M2 HTTP 요청의 durable in-flight 기록을 수정했고, 추가 카운터 회귀까지 독립 재검토에서 ADDRESSED / scoped quality Approved로 마감했다. 실서비스 반영과 실제 URL 검증은 이번 범위에서 제외하고 다음 한도로 이관한다. 수정 후 지정90 passed/5 PostgreSQL 조건 skips, 이후 카운터 정정 대상1 passed와 Ruff 통과다. 마지막 수정본의 전체 실PG 검사는 아직 실행하지 않았다. 완료 증거는 작업 원장 `work/verification/m2a/progress.md`와 [최종 검토](reviews/m2a-review.md)에 추가한다.

수정 전 전체 검증은 실PG342 passed/4 skipped, Chromium fixture26 passed/22 filtered skips다. 이 결과를 수정 후 결과로 재사용하지 않는다. 실행 중인 서비스는 M1이며 공개 DB의 마지막 관찰값은 migration0002/분석19건이다. 준비한 Docker 이미지는 최종 수정 전 candidate이므로 다음 실제 반영 전에 **재빌드가 필요하다**.

## 이전 진행 기록

## 최신 상태 — M2 착수 지시 수신

최신 진행: 사용자 “가자”·“진행해줘”로 승인한 [M2-A 구현계획](superpowers/plans/2026-11-11-m2a-evidence-review.md)의 Task1~4는 작업별 독립 검토·수정·재검토를 통과했다. 실제 모델 schema의 역할·도구 enum 경계 보완도 독립 검토를 통과했으며 현재 Task5 독립 시스템 검증을 진행한다. 소유와 정확한 요구는 `work/verification/m2a/model-contract-brief.md`, 원장은 `work/verification/m2a/progress.md`다. 현재 소스는 이 보완을 포함한다. 새 모델·검색 요청, M2 실행 반영, 실제 URL 검증은 아직 수행하지 않았다. 점수·추천은 후속이다.

Task3 실PG 전체 319 passed/3 skipped는 DTO 마지막 수정 전 증거다. Task4는 fix1 전체 fixture E2E 25 passed/21 filtered skips, fix2 관련 3 passed/3 filtered skips와 빌드를 통과했다. 최종 전체 검증은 수정 후 수행한다. 기존 public DB는 migration0002, 분석19건을 보존한 상태다. 아래 승인 대기·미진입 문장은 당시 이력이다.

### 이전 착수 기록 — 상세 설계 승인 전

사용자의 **“M2 시작하자”**로 이전 보류가 해제됐고 **“A 가자”**로 조사 흐름 먼저 구현하는 순서를 선택했다. M2는 기존 Supervisor+고정 전문5역할, 근거 조사·선택적 재조사·종합 평가 방향을 유지한다. 현재 [M2-A 설계 초안](superpowers/specs/2026-11-11-m2a-evidence-review-design.md)의 사용자 상세 승인 대기다. Luna runtime 조사와 별도 builder check·질문3개 해소 후 재확인을 마쳤고 기존 모의 회귀75개가 통과했다. 제품 코드는 아직 변경하지 않았다. 점수·추천은 M2 후속이며 초안의 예산/복구 제안도 아직 구현·실검증되지 않았다. EGM 전체 검토는 수행하지 않았으므로 builder check를 EGM 검토 통과로 해석하지 않는다. [M2 착수 기록](m2-kickoff.md)을 먼저 읽으며 아래 보류 상태는 과거 이력으로 해석한다.

## 이전 상태 — 2026-11-11, M2 미진입

사용자는 **“M2진입하지마”**라고 명시했다. M2 설계·구현·착수는 보류한다. 고정20URL baseline은 HTML16/수집오류4, 모델15완료·직접추출1·공식26요청으로 마쳤고 원본 라벨/결과를 보존했다. matched2건은 독립 사후 판정으로 읽었으며 원래 known1/unknown1의 분모를 바꾸지 않았다. 마지막 placeholder/제조역할 guard를 실행 반영했고 신규 ER15 URL-only 구조화 경로(모델0)·DB/권한 조회 회귀를 통과했다. 마지막 guard 독립9개 회귀·Ruff·diff와 오프라인 cache hash 검증까지 마쳤으며 배정된 M1 한정 점검 범위의 필수 미해결 사항은 없다. M2는 보류·미진입 상태로 종료한다. [한정 평가 결과](evaluation/m1-results.md)를 우선 읽으며 아래 이전 완료·진행·M2계획은 이력이다.

## 이전 기본 기능 마감 — 2026-11-10

합의한 M1 기본 기능과 판매명 차이 등록 대조 경로의 구현·독립 검증·실행 반영을 마쳤다. 최종 새 URL-only 분석 `d006f66a-5e04-469c-acc7-ce4a293839a7`은 실제 표 직접 읽기(`structured_page`, 모델0) → 실제 I0030 대조 → DB completed → 토큰 조회를 통과했다. 주요 원료3종·번호·제조사와 판매명 차이를 명시하며 점수는 없다. 독립 관련93회귀, 관련 Chromium desktop/mobile2개·build·시각 확인, 실행본 해시/readiness도 통과했다. [최종 범위·증거·한계](m1-closeout.md)를 우선 읽는다. 아래 과거 미달/선택 대기는 당시 기록이다. 모델만 사용하는 페이지의 timeout·누락과 원래 국내3표본의 한계는 보존하며 일반 성능을 주장하지 않는다.

## 고정평가 진행 이력 — 2026-11-11

고정20URL 평가 Stage0은 HTML16/SSG HTTP오류4/구조화 추출1/모델0·공식0으로 완료했다. 동일URL 독립 라벨 v2를 freeze했고 최종 하네스 QA31개·Ruff/help/diff를 통과했다. root가 별도출력 Stage1 모델/API 실측을 진행 중이며 아직 결과·M2 진입을 확정하지 않았다. 완료 후 matched 전건을 원래 라벨과 분리한 독립 사후 판정으로 읽고 지원 입력조건·치명 오류·M2 게이트를 닫는다.

**새 사용자 선택: M1 평가를1~2일 상한으로 제한한 뒤 M2로 진행.** 지원 후보3~5사이트의 고정URL20개를 baseline 전에freeze하고 무모델관찰·정답라벨·bounded실측·치명오류수정·지원범위를 남긴다. 새평가게이트는 `docs/evaluation/m1-gate.md`, root소유manifest는 `docs/evaluation/m1-corpus.json`이다. Luna하네스작성자와새독립QA를 호출해구현중이며 아직20개baseline실측결과는없다. 기존단일URL반복진단·편의표본은새baseline에합치지않는다. 제품코드추가확장/OCR/JS/새모델은하지않는다.

사용자는 확률 표시 없이 번호·제조사·주요 기능성 원료 대조와 비교 가능한 함량/제형 모순 검사를 묶어 판매명 차이를 드러내는 기준을 승인했다. 계약 말미의 새 경로를 Luna backend/frontend가 구현 중이며 작성자 분리 QA·신규 URL 실검증은 아직 대기다. 응답 대기였던 아래 이름 정책은 이 승인으로 해소됐다. 일반 부원료만으로 확인하지 않으며 이전 자동positive0을 새 결과 전 성공으로 바꾸지 않는다.

사용자가 이어서 진행을 명시했다. 안전한 실패 분류로 신규 timeout을 확인한 뒤 reasoning low/none을 유한하게 검증했다. 최종 실행본은 같은 GPT-5.6 Luna의 none·collection snapshot5이며 모델/원문/스키마/15초·매칭조건은 유지했다. KGC는 low에서 추출성공 뒤 동명 제조사2등록으로 candidate, 별도 ER Hana는 none에서 추출·공식번호조회성공 뒤 판매명과 등록명이 달라 candidate였다. 독립 자동확정0은 유지하며 번호·제조사·추가성분 일치 시 이름 차이를 다루는 규칙은 사용자 선택 대기다. 응답 전 매칭코드를 바꾸지 않는다. 새 Luna 작성자와 독립 QA의 최종73개 회귀·Ruff·diff는 통과했으며 실증거 독립 읽기도 마쳤고 최종 실행 manifest `work/verification/2026-11-10-m1-deployment.json`은 passed다. API/worker/host 및 frontend 코드 동일성·readiness·migration0002를 확인했고 전체 hash는 `2026-11-10-m1-source.sha256`에 보존한다. 과거의 미분류 request_failed를 소급해 timeout으로 단정하지 않는다.

## 이전 상태 — 2026-11-09

**자동 매칭 개선 구현·검증 루프 종료 — 자동 확정 목표 미달.** 최종 신규 URL1회는 수집성공 뒤 모델 request_failed로 needs_input, 공식조회0이었으며 자동 성공을 입증하지 못했다. 현재 안전한 후보 대조 구현은 Compose에 실행 반영했고 readiness/migration0002/API·worker hash 일치를 확인했다. 추가 모델 호출 없이 실패 증거도 보존했다. 상세는 verification.md와 `work/verification/2026-11-09-automatic-matching-url.json`을 따른다. cached 독립 원문 2건의 실제 I0030 재대조 결과는 matched0/candidate1/unverified1이며 원래 3시도 중 수집실패1은 제외했다. 에브리타임샷은 이름·제조사·부원료가 일치하는 신고2건이 있어 정직하게 candidate로 남긴다. 후보 검색/설명 개선과 자동 확정 성공을 구분한다. 사용자의 실행 한도 내 종료 요청에 따라 현재 필수 QA·배포·마지막 URL1회 증거만 마무리한다.

**재개: 자동 매칭 개선 진행 중.** 이전 추가 입력 경로 완료는 URL 자동 매칭 목표 완료를 의미하지 않는다. 사용자는 URL 원문→제품정보→공식 후보→다중근거 대조 개선을 승인했다. 최신 계약은 contracts.md 마지막 항목, 작업·종료 기준은 tasks.md 마지막 항목이다. 작성자 Luna backend/frontend 구현 후 새 독립 QA와 실제 API 대조·실행 반영이 남아 있다. 아래 완료 표현은 추가 입력 경로에만 적용한다.

사용자가 선택한 M1 추가 정보 1회 보완 경로의 구현·독립 QA·실제 통제 연동 검증을 마쳤다. 정보 부족 보고서의 권한 있는 비회원만 한 묶음을 제출하고, 누적 예산/시도를 보존해 공식 자료를 재대조하며 판매 페이지와 사용자 입력 출처를 구분한다. Backend 독립 관련 검사38 passed/18 PG skips, 실제 Chromium15 passed/13 viewport skips, build/Ruff/desktop·mobile 시각 확인 통과. 작성자의 실제 PG 동시 수신 검사와 별도 실PG/Redis/Celery/I0030 통제 보완 1건도 통과했다. 최종 evidence 독립 대조를 마쳤다. 세부 원문·검증본 hash는 `docs/verification.md`, `docs/reviews/m1-supplement-review.md`에 있다.

국내 자동 매칭 표본은3시도·2수집·실모델2완료지만 신고번호를 확보하지 못해 독립 positive0이었다. 실통합 positive는 공식 record 유래 수동 입력/통제 DB seed이며 자동 매칭 성능으로 세지 않는다. 전체 제품 평가·점수·추천·회원·이미지 판독은 후속 범위다. 최종 DB/broker readiness, migration0002, API/Worker/Frontend 검증 소스와 실행본 hash 일치까지 통과했다. 원문은 `work/verification/2026-11-09-supplement-deployment.json`, manifest는 `2026-11-09-supplement-source.sha256`다. 이번 추가 입력 구현·검증 루프는 완료했다. 이전 절의 미검증/선택 대기 상태는 각 시점의 이력이다.


기준일: 2026-11-07. 최종 실행 작업공간은 `/Users/hyeonseokbae/Desktop/ad_fact_check`다. 원본 소스를 보존하고 Desktop으로 복사했으며, 최종 Compose 재빌드·실제 접수·권한 조회·fixture 복구 검증까지 통과했다. 최신 상태는 실제 파일과 `docs/verification.md`를 함께 확인한다.

## 구현 상태

M1 경로의 PostgreSQL 마이그레이션·원자적 lease/claim·누적 예산·snapshot, SSRF 방어 HTTPX 수집기, LangGraph 수집 보고서, FastAPI 비회원 토큰 조회, Celery 작업·15초 beat 복구, 비공개 원문 파일 저장, React/TypeScript/Vite 화면과 Compose를 구현했다. 완성된 전체 제품 평가나 회원 기능으로 해석하지 않는다.

DB/수집/Agent/API 모의 검사와 실제 PostgreSQL 저장소 검사, 실제 Docker의 DB→Redis→Celery→example.com→보고서 저장·guest 조회 경로를 확인했다. 독립 리뷰에서 토큰 오류 일관성, 숫자 함량 grounding, Celery 시간한도 정렬, API 이벤트 루프 차단, IPv6 site-local 거부의 필수 수정 5건을 해결했다. 관련 회귀 64 passed, 독립 회귀 5 passed이며 `docs/reviews/m1-review.md`에 검증 코드 해시를 기록했다.

## 이어서 작업하는 방법

`AGENTS.md`, 범위·아키텍처·계약·작업판·검증 기록과 실제 소스를 읽는다. 개발 리드는 GPT-6.1 Sol, 이후 구현·검증 서브에이전트는 GPT-6 Luna 기본값이다. `.codex/config.toml`과 `scripts/start-codex.sh`가 이를 보존하며 서비스 내부 모델 GPT-5.6 Luna와 구분한다. 시작은 `bash scripts/start-codex.sh`, 로컬 실행은 `bash scripts/start-local.sh`다. Python은 uv 잠금 파일과 3.11 환경을 사용한다.

프로젝트는 최초 커밋 전 상태다. 사용자 변경을 보존한다. 이전 실행 세션의 Agent가 유지된다고 가정하지 않는다. 복구는 DB의 queued/expired running 재발행과 claim fencing, 노드 snapshot 재사용이며 완전한 임의 위치 resume를 보장하지 않는다.

## 미검증·후속 범위

2026-11-09 추가: 공개 실제품 무키 샘플에서 Solgar 수집·보고서 계약은 통과했고 NOW는 HTTP 오류였다. 실제 prefork child SIGKILL과 hard-timeout fixture는 별도 Compose 스택에서 각각 기본 240초 lease 자연 만료 후 복구·fencing·누적 예산을 확인했다. OpenAI 가상 표시 1건의 구조화 추출과 FoodSafety I0030의 20개 record 응답 파싱에 이어, 실제 Solgar 공개 제품 1건의 접수→모델 추출→공식 조회→저장·토큰 조회 경로를 확인했다. 제조사·신고번호가 없어 needs_input/공식 unverified였으며 점수를 만들지 않았다. 국내 공식 등록이 verified로 일치하는 실제 positive 사례와 폭넓은 추출 품질은 아직 미검증이다. 새 하네스는 독립 QA를 거쳤으며 정확한 원문·한계는 `docs/verification.md`와 `docs/reviews/m1-completion-review.md`에 있다. 브라우저 host는 재시도에서도 불가했다. 아래 무키 상태는 최초 검증 당시의 기록이다.

OpenAI·FoodSafety 키가 없는 환경에서 M1을 검증했다. 실제 모델 구조화 추출, 공식 제품 조회·매칭 품질과 비용은 미검증이다. 설정된 키를 반환하거나 로그로 출력하지 않는다. Clerk 회원 인증, 5개 전문 Agent의 조사·평가·점수, 이미지/수동 추가 입력, Tavily·LangSmith·R2, kind 장애 실험은 후속 마일스톤이다. API의 미설정 기능을 가짜 성공으로 바꾸지 않는다.

추가 수정: 실제 I0030 전체 이름 검색이 기존 record를 돌려주지 않는 사례를 발견해, 추출 신고번호가 있으면 번호로 검색하고 세 identity 필드의 엄격한 일치는 그대로 유지했다. 관련 독립 24 passed/Ruff 통과. 공식 record 유래 통제 입력의 실API 양성 verified/제조사 오류 음성 unverified 재검증도 통과했다. 이는 국내 판매 페이지에서 독립적으로 식별한 제품의 positive match 품질과 구분한다.

최종 실행 반영: 2026-11-09 수정본을 API/Worker/Beat에 재빌드·반영했다. DB/Redis readiness와 검증 코드·실행 코드 동일성을 확인했다. 실행 위치는 계속 Desktop/ad_fact_check이며 원본 이전 폴더를 다시 동기화하지 않았다.


## 현재 추가 확인 작업 — 2026-11-09

핵심 M1 구현·기존 실연동 검증과 사용자 요청 추가 확인의 상태를 구분한다. 국내 3제품·최소 2제조사의 독립 판매/제조사 원문과 I0030 대조를 소규모로 확인 중이며, 공식 record 유래 통제 입력은 그 독립 표본에 포함하지 않는다. 사용자는 Playwright 실제 브라우저 자동 검증을 명시적으로 선택했다. Playwright는 개발 테스트에 사용하며 제품 HTTPX 수집기의 기술을 바꾸지 않는다. 화면 테스트 API fixture와 국내 실제 모델/API 증거를 구분한다. 유한한 M1 종료 조건은 `docs/tasks.md`의 종료표를 따른다. 이 항목은 결과가 나오기 전 완료를 뜻하지 않는다.


국내 추가 확인 실행 결과: 원래 3제품 중 2페이지를 HTTPX로 수집했고 서로 다른 제조사 2건에서 실제 모델 추출을 완료했다(총 유료 모델 2콜). 락토핏 골드 17포와 에브리타임 샷 모두 제품명·제조사는 추출됐으나 신고번호가 HTML 텍스트에서 확인되지 않아 공식 대조는 unverified, 독립 positive 0건이었다. 고려은단 SSG는 HTTP 오류다. 원문·분모·병합 provenance는 `docs/verification.md` 및 `work/verification/2026-11-09-domestic-matching-live.json`에 있다. **검사 실행 결과와 매칭 품질 충분 판정은 다르며, 이 표본 확인 당시 M1 전체 완료 판정은 보류했다.** 이후 사용자가 선택한 추가 입력 M1은 새 범위의 완료 기준으로 검증하며 자동 매칭 한계는 유지한다. 추가 정보 입력/이미지 판독을 M1으로 앞당길지 현행 텍스트 범위를 유지할지 사용자 선택을 기다리며 제품 기능 확장은 하지 않았다. 화면은 전용 5174 실제 Chromium 9개 시나리오(반대 project 조합 9 skip)와 build를 통과했고 독립 QA가 전용 서버 격리·정상 세션 복원·정상 보고서 캡처까지 재확인했다. 국내 하네스 독립 QA도 통과했다. 사용자는 이후 추가 정보 입력을 M1으로 앞당기기로 선택했으며 새 기능 구현 중이다.


## 추가 입력 M1 구현 루프 — 2026-11-09 재개

사용자는 추가 정보 입력을 M1에 포함하기로 선택했고 이후 이어서 진행하라고 명시했다. API/DB/Worker와 Agent 보완 경로의 작성자 구현·관련 검사는 완료됐으며 Frontend의 1회 보완 폼·사용자 입력 출처 표시·브라우저 검사를 구현 중이다. 이전 추가 검증 QA는 끝났지만 새 보완 기능의 독립 QA·실제 PostgreSQL/Redis/Celery/I0030 경로·최종 화면 확인은 아직 완료되지 않았다. 이 루프는 키를 추가 출력하거나 모델을 재호출하지 않고 저장 보고서와 사용자 보완값으로 공식 등록만 재대조한다.

앞선 새 QA 호출은 사용량 제한으로 실패했고 완료로 세지 않았다. 사용자 재개 후 독립 QA를 다시 실제 호출했다. 최신 상태는 실행 결과와 `docs/reviews/m1-supplement-review.md`를 함께 확인한다. 개발 리드는 공통 계약과 통합을 맡고 API/DB/Worker·Agent·Frontend 작성자와 최종 QA를 분리한다.
