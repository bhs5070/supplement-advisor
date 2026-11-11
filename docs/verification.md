# 검증 기록

## 최신 실행 범위 — 2026-11-11

**M2는 사용자 명시 지시로 보류·미진입이다.** M1 마지막 identity guard 독립9개 회귀·Ruff·diff·기록까지 마쳤다. 한정 점검 범위의 필수 미해결 사항은 없으며 다음 단계는 실행하지 않는다. 기술적 평가 게이트 판정은 M2 착수와 구분한다. 아래 실행/실패/변경 증거는 원래 시점 그대로 보존한다.

최신 완료 범위와 실패 이력은 [2026-11-10 M1 마감](m1-closeout.md)을 우선 읽는다. 최종 새 URL 실제 등록 대조·저장·권한 조회와 독립93개 관련 회귀를 통과했다. 아래는 누적 검증 이력이다.

기준일: 2026-11-07. 모의 검사·실제 인프라·외부 서비스 품질 검증을 구분한다. 1차 인프라 결과와 필수 수정 뒤 회귀 결과를 함께 기록한다. 최종 Desktop 재실행 결과는 아래 기록에 추가한다.

| 범위 | 실행/결과 |
|---|---|
| DB 격리·동시성 | `TEST_DATABASE_URL=... .venv/bin/python -m pytest tests/test_repository.py -q`: SQLite + 실제 PostgreSQL 합계 29 passed, SQLite에서 PostgreSQL 전용 검사 1 skipped |
| 수집기 | `pytest tests/test_collection.py`: 모의 HTTP/DNS 안전경계 30 passed |
| LangGraph | `pytest tests/test_agents.py`: 모델·공식 API 모의 응답 16 passed |
| API/Worker | `pytest tests/test_api_worker.py`: 6 passed |
| 실제 인프라 | Docker Compose PostgreSQL/Redis healthy, migration 및 체크포인트 setup exit 0, API/Worker/Beat 실행 |
| 실제 수직 기능 | `.venv/bin/python scripts/verify_live.py`: `live_stack passed`, example.com 실수집→needs_input, collection_only 보고서 저장·조회. 내부 URL 422, 무토큰/틀린 토큰 404 |
| 필수 수정 뒤 관련 회귀 | `.venv/bin/python -m pytest tests/test_review_regressions.py tests/test_collection.py tests/test_agents.py tests/test_api_worker.py -q`: 64 passed. 지정 소스/테스트 Ruff 통과. Celery finalize 후 실제 process task hard60/soft59 확인 |
| 독립 리뷰 | `docs/reviews/m1-review.md`: R1–R5 수정 후 독립 QA 5 passed. 시간한도·긴 토큰404·함량 grounding·threadpool·site-local 거부 확인. 코드 해시는 리뷰 보고서에 기록 |
| 실제 복구/중복 | `.venv/bin/python scripts/verify_recovery.py`: 발행 누락 queued 행을 실제 beat→Redis→Celery가 처리(attempt 1/예약60), 만료 lease fixture는 attempt2/누적예약120. terminal에 동일 ID 3회 발행해도 attempt 불변. DB fixture 복구이며 실제 Worker kill 아님 |
| Frontend build | `cd frontend && npm run build`: TypeScript 및 Vite 7.3.7 production build 통과. 실제 프런트 HTML HTTP 200 및 `/api/health` Vite proxy 응답 확인. 브라우저 렌더 동작은 미검증 |
| 개발 CLI | `bash -n scripts/start-codex.sh`, `bash scripts/start-codex.sh --check`: 통과(codex-cli 0.160.0). 프로젝트 Sol/Luna 기본값 반영 |

## 제품 실행 예산 해석

DB의 claim/예약 전 제어 구간은 제품의 활성 조사 구간과 구분한다. 수집·외부 도구를 실행하기 전에는 시도 전체 창을 DB에 commit해 선예약하고 중단 후 환급하지 않는다. Celery prefork의 process hard limit이 그 예약 창을 넘지 않아야 동기 파일/DB 호출 지연도 예약을 초과하지 않는다. asyncio timeout만으로 동기 I/O 중단을 보장한다고 주장하지 않는다. 기본 최대 시도는 3회이며 총 예약은 180초/도구 20회 이내다. 대기/lease 만료를 활성 시간에 더하지 않는다.

## 최초 검증 당시 미검증 — 2026-11-07

- 브라우저 UI 시각 검증은 CUA browser host unavailable로 수행하지 못했다. TypeScript/Vite build 및 프런트 HTTP·API 프록시 검증과 구분한다.
- OpenAI·FoodSafety API 키가 없어 실제 모델·공식 조회·매칭 품질은 검증하지 않았다. 모델·공식 조회 결과를 모의 성공으로 대체하지 않는다.
- 강제 worker kill 중 정확한 prefork hard-timeout 동작은 별도 장애 검증 결과가 없는 한 미검증이다. queued/expired-row 회복 검사는 실제 프로세스 kill과 구분한다.
- Clerk·개인화·전체 제품 평가·점수·영양소 안내·이미지 추가 입력·Tavily·LangSmith·R2·kind는 M1 범위가 아니다.
- 대량 부하·비용·실제품 수집률과 임상적 판단 품질은 측정하지 않았다.

## Desktop 최종 검증

최종 실행 경로: `/Users/hyeonseokbae/Desktop/ad_fact_check` (2026-11-07).

- `docker compose up -d --build`: API/Worker/Beat/Frontend 실행, DB·Redis healthy, migrate exit 0.
- 새 위치의 Python 3.11 환경에서 관련 회귀 64 passed, Ruff 통과. 원문: `work/verification/final-regressions.log`.
- `scripts/verify_live.py`: 실제 네트워크/DB/큐 경로 통과. 분석 `f23a7189-9146-49e7-b3e0-a1e0004ab336`, needs_input/collection_only. 외부키 미설정을 그대로 반환.
- `scripts/verify_recovery.py`: 미발행 queued 작업은 attempt 1/예약 60초, 만료 lease fixture는 attempt 2/누적예약 120초로 복구. 동일 ID 3회 재전달에도 추가 점유 없음. 실제 프로세스 kill 검사가 아니다.
- 화면 HTTP 200 및 `http://localhost:5173/api/health` 실제 API proxy 응답 확인. 브라우저 렌더·클릭 확인은 위 환경 제약으로 미검증.
- `bash -n scripts/start-local.sh scripts/start-codex.sh`, `bash scripts/start-codex.sh --check`: 통과. codex-cli 0.160.0, 새 프로젝트 경로와 인계 파일 확인. sandbox PATH alias 경고는 출력됐으나 검사 종료 0.
- 원본 경로의 소스를 보존했다. 이후 작업과 실행은 Desktop 경로를 기준으로 한다. 최초 커밋 전 상태이며 자동 커밋하지 않았다.

## M1 잔여 검증 재개 — 2026-11-09

- 로컬 키 입력용 `.env`를 생성했다. 파일 존재나 `/api/capabilities`의 `configured_unverified`는 실제 인증·모델 접근·공식 제품 일치 성공의 증거가 아니다. 키를 검사 출력이나 문서에 기록하지 않는다.
- CUA 재시도에서도 native service startup 및 browser access host가 unavailable이었다. 이번에도 브라우저 렌더·클릭 검증을 수행하지 못했으며 기존 build/HTTP proxy 증거와 구분한다.
- 실제 prefork 장애 검증은 기존 서비스와 분리한 Compose project·DB·Redis·Worker·Beat에서 수행했다. 느린 수집·저장 fixture 주입은 외부 연동 품질 검증이 아니며, 기존 expired-row fixture 검사와 실제 프로세스 종료 증거를 구분한다. 결과는 아래에 기록했다.
- 실제품 소규모 검사는 실제 공개 HTTPS 수집과 `run_collection_graph`를 직접 연결한다. 기존 API 저장·조회 검사와 별개이며, 소수 페이지 결과를 전체 수집률·임상 품질·국내 공식 제품 매칭 정확도로 일반화하지 않는다.
- 품질 도구의 종료 코드 0은 수집·보고서 계약 검사를 통과했다는 의미다. 모델 요청 실패를 정직하게 `unavailable`로 표시해도 계약은 통과할 수 있다. 모델 실연동 성공은 추출 check 상태와 실제 원문에 근거한 비어 있지 않은 추출을 확인해야 하며, 공식 제품 일치는 별도 check로 판정한다.

### 공개 실제품 소규모 검사

`scripts/verify_product_quality.py`는 기본 실행에서 설정된 키를 무시한다. `--use-configured-keys`로 명시한 경우에만 외부 모델·공식 API 호출을 허용한다. 키 설정 여부를 실제 호출 성공으로 표시하지 않으며 사용자 URL의 query·fragment·userinfo를 출력에서 제거한다.

작성자 실행 결과: `tests/test_product_quality_harness.py` 9 passed 및 Ruff 통과. 승인된 실제 HTTPS 검사에서는 NOW Foods Vitamin D3 5000 IU 제조사 상품 페이지가 `http_error`, Solgar Vitamin C 1000 mg 제조사 상품 페이지는 수집 성공이었다. Solgar 보고서는 출처와 4개 check를 보존하고 `score=null`, `verdict=hold`, 제품명·제조사·성분표 누락을 표시했다. 외부키를 사용하지 않아 추출·공식 대조는 unavailable, 추출·grounding 품질은 미평가다. 미국 제조사 상품 페이지 두 사례이며 국내 I0030 매칭 품질이나 전체 수집률의 증거가 아니다. sandbox 네트워크 실패와 승인 후 실제 사이트 응답을 구분했다.

작성자의 첫 무키 실행은 stdout만 남아 원문 보관이 누락됐다. 원문 증거 확보를 위해 루트가 동일 무키 샘플을 한 번 재실행했다: `.venv/bin/python scripts/verify_product_quality.py --output work/verification/2026-11-09-product-quality.json`. `mode=no_external_calls`, NOW `http_error`, Solgar `quality_issues=[]` 및 추출 미평가를 재확인했다. 일부 페이지 수집 실패 때문에 종료 코드는 설계대로 1이었다. 이 JSON을 실제 HTTPS 결과 원문으로 보관한다. 독립 QA는 네트워크를 재실행하지 않고 하네스·URL 비밀값 제거·무키 기본값을 검토했다. 독립 단위 검사 9 passed, 장시간 통합 검사 1 deselected이며 `docs/reviews/m1-completion-review.md`에 파일 해시와 한계를 기록했다.

### 실제 prefork 프로세스 장애 검증

`.venv/bin/python scripts/verify_process_recovery.py`는 exit 0, `process recovery verification passed`였다. 별도 `m1-process-recovery-kill` 및 `m1-process-recovery-timeout` 프로젝트의 DB·Redis·Worker·Beat를 사용했고 호스트 포트는 노출하지 않았다. 제품의 `process_analysis`/`execute_analysis`와 claim·예약·fencing·종료 경로를 유지하고 test-only bootstrap에서 수집·저장만 fixture로 주입했다. 외부 URL·모델·공식 API를 호출하지 않았다.

- 실제 실행 중인 prefork child에 SIGKILL을 보냈고 WorkerLostError를 검사했다. lease 전 재전달은 새 claim을 얻지 못했다.
- 별도 시나리오의 동기 저장 fixture는 29초 soft limit을 무시했고, 30초 hard limit의 TimeLimitExceeded 및 child 종료를 검사했다. 실제 제품의 기본 시도 창 60초 대신 격리 설정 30초를 사용했다.
- 두 시나리오 모두 기본 lease 240초를 강제로 바꾸지 않고 자연 만료를 기다렸다. 15초 beat 재발행 후 attempt 2, 예약 30→60초, 도구 호출 1→2, 이전 claim의 `finish=False`, 최종 `needs_input`을 확인했다. 느린 fixture는 실제 외부 연동·처리량 측정이 아니다.
- 두 테스트 스택은 `docker compose down`으로 종료했고 `-v`를 사용하지 않아 볼륨을 보존했다. 기존 앱 서비스는 전후 Up, DB·Redis healthy였다. 중간 기존 API/Worker/Beat 재생성은 사용자가 입력한 키 반영을 위한 루트의 별도 작업이었다.

실행 stdout/stderr 및 범위 기록: `work/verification/2026-11-09-process-recovery.log`. Worker 상세 로그는 하네스가 실행 중 검사했지만 별도 원문 파일로 보관하지 않았다. 기본 pytest는 외부 Docker 장애 실험을 자동 실행하지 않으며 `RUN_PROCESS_RECOVERY=1`에서만 실행한다. 기본 검사 1 skipped, Ruff·Compose config 통과. 앞의 11월 7일 worker 장애 미검증 항목은 이 한정된 실제 fixture 장애 검증으로 보완됐다.

### 외부 서비스 실인증·구조화 출력

사용자가 두 키의 로컬 입력 완료를 알린 뒤 실행했다. 키 값은 출력하거나 보관하지 않았다. API/Worker/Beat도 새 설정으로 재생성했다.

- 공개 Solgar 한 페이지를 명시 opt-in으로 시도했지만 이번에는 `http_error`로 수집되지 않아 모델 호출이 발생하지 않았다. 원문: `work/verification/2026-11-09-openai-product-quality.json`. 앞선 무키 수집 성공과 다르며 사이트 응답 변동의 원인이나 수집률을 단정하지 않는다.
- 고정 가상 표시 1건을 실제 OpenAI Responses 구조화 추출에 넣어 제품명·제조사·신고번호 및 비타민C `100 mg`의 원문 기반 추출을 확인했다. `표시 정보 추출` check는 `unverified`(표시 추출 완료, 실제 효과 미검증), `score=null`이었다. 원문: `work/verification/2026-11-09-openai-synthetic.json`. 이는 synthetic 입력의 실인증·구조화 출력·grounding 경로 검사이며 실제 공개 제품 추출 품질 검증이 아니다.
- 식품안전나라 I0030에 `비타민`을 조회해 실제 응답 20개 record와 제품명·제조사·신고번호 필드의 파싱을 확인했다. 원문: `work/verification/2026-11-09-food-safety-auth.json`. 인증·응답 파싱의 증거이며 판매 페이지 제품과 공식 등록의 동일성이나 매칭 품질을 검증한 것은 아니다.

### 두 키 설정 후 실제 공개 제품 수직 경로

Solgar Vitamin C 1000 mg Vegetable Capsules 공개 상품 페이지를 API에 제출해 실제 PostgreSQL→Redis/Celery→HTTPX→OpenAI 구조화 추출→I0030 조회→보고서 저장→비회원 토큰 조회를 확인했다. 분석 ID는 `dc811b25-4ca6-4c73-9610-4fb174001971`, 원문은 `work/verification/2026-11-09-configured-live-stack.json`이다. 올바른 토큰 조회는 200, 무토큰 조회는 404였다. 조회 토큰은 산출물에 보관하지 않았다.

제품명, 광고·표시 문구 8개, 성분 4개를 추출했다. 비타민C는 원문의 `1000 mg`와 `Amount Per Serving` 기준을 보존했고 다른 성분의 없는 함량은 null이었다. 제조사와 신고번호는 확인되지 않아 API 상태는 `needs_input`/`insufficient_information`, 요청 누락 필드는 `manufacturer`였다. 공식 등록 check는 `unverified`로 남고 미등록·불법을 단정하지 않았다. `scope=collection_only`, `score=null`, `verdict=hold`, 비회원 개인 적합성 미평가를 유지했다.

실모델 유료 호출은 가상 표시 1건과 실제 공개 제품 1건의 총 2건이었다. 앞의 tablets 페이지 수집 실패는 모델 호출 0건이었다. 이 1개 공개 제품의 수집·추출·저장 경로 성공을 전체 제품 평가나 국내 공식 등록 positive match의 품질 증거로 일반화하지 않는다. 국내 제품명·제조사·신고번호가 모두 일치하는 실제 `verified` 예시는 아직 미검증이다.

### 공식 동일성 분기 추가 조사

실제 I0030 `비타민` 조회의 첫 record에서 제품명·제조사·신고번호를 그대로 가져온 통제 입력을 `_check_official`에 전달한 양성 분기 검사도 `identity_not_confirmed`/`unverified`였다. 제조사를 바꾼 음성 분기도 unverified였다. 원문은 `work/verification/2026-11-09-food-safety-matching.json`이다. 같은 공식 record의 양성 일치를 확인하지 못했으므로 실제 matcher positive 검증을 통과로 처리하지 않는다. 검색 필터·결과 집합·동일성 비교의 원인을 조사 중이며 판매 페이지의 독립적인 제품 식별 품질 검사와는 별개다.

추가 실제 조회에서 첫 제품의 긴 전체 이름(공백·중점·더하기 기호 포함)은 0개 record, 다른 제품의 전체 이름은 1개 exact record를 반환했다. `work/verification/2026-11-09-food-safety-diagnostic.json`에 기록했다. 첫 제품을 공식 신고번호 필터 `PRDLST_REPORT_NO`로 직접 조회하면 HTTP 200/INFO-000, 1개 record와 원본 제품명·제조사·번호의 일치가 확인됐다(`work/verification/2026-11-09-food-safety-number-filter.json`). 따라서 표시에서 신고번호가 확인된 경우 그 번호로 검색을 좁히고, 응답의 세 필드는 계속 엄격히 비교하는 최소 수정을 진행했다. API의 전체 이름 검색 차이의 내부 원인이나 모든 특수문자 동작을 단정하지 않는다.

수정은 `agents/collection_graph.py`의 optional `report_number` 검색 인자와 단일 호출부에 한정했다. 번호가 없으면 이름 검색을 유지하며 이름·제조사·번호 전체의 정확한 정규화 일치와 유일한 결과만 verified로 처리한다. 작성자 모의 Agent 검사 19 passed 및 Ruff 통과, 별도 Luna QA의 Agent+독립 회귀 검사 24 passed 및 Ruff 통과, 필수 지적 없음이었다. 수정 후 실제 API 양성 재검증은 별도로 기록한다.

수정 후 같은 공식 record 유래 통제 입력으로 실제 API를 다시 2회 조회했다. 세 필드가 같은 양성은 `verified`/`registration_matched`, 제조사가 다른 음성은 `unverified`/`identity_not_confirmed`였다. 원문: `work/verification/2026-11-09-food-safety-matching-fixed.json`. 모델 호출은 없었다. 이전 실패 산출물도 보존했다. 이는 실제 I0030 검색·동일성 matcher 양성/음성 분기 검증이며, 판매 페이지에서 독립적으로 식별한 국내 제품의 정확도를 입증하지 않는다.

### 2026-11-09 최종 서비스 반영

수정본 `docker compose up -d --build api worker beat` 종료 0. API/Worker/Beat/Frontend 실행, DB·Redis healthy, migrate 종료 0. `/api/ready`에서 database/broker 모두 true. 두 키 설정 상태는 확인했으며 실제 연동 결과는 위 개별 원문과 구분한다. 실행 Worker의 Agent 코드 SHA-256은 호스트 검증본과 동일한 `60c85a7cb98c97a09a77dcd36a8e71063fcd9c38e678d12a83dcc3a32b5cb147`이다. 전체 소스 식별자는 `work/verification/2026-11-09-source.sha256`에 보관했다. `.env`는 버전 관리 제외를 확인했고 키 값을 기록하지 않았다.


## 국내 제품·화면 추가 확인 — 2026-11-09 (진행 중)

이번 확인은 M1의 수집·식별 범위에서만 수행한다. 국내 독립 판매/제조사 페이지 3개·최소 2개 제조사를 작은 표본으로 관찰하고, 페이지에서 얻은 제품명·제조사·신고번호를 실제 I0030과 비교한다. 원문에서 확인되지 않는 번호나 제조사는 공식 API 값을 가져와 채우지 않는다. 공식 API 재가공 DB는 독립 판매 원문 표본에 포함하지 않는다. 통제 음성 입력은 실제 페이지 표본과 별도로 표시한다. 수집 성공, 모델 호출/완료, 세 identity 확인, 공식 조회, 최종 일치의 분모를 각각 기록한다. 이 표본을 국내 전체 매칭 정확도로 일반화하지 않는다.

사용자는 Playwright 실제 브라우저 검증을 명시적으로 선택했다. 개발 테스트에서 실제 React/Vite 화면과 Chromium을 사용하고 API는 route fixture로 대체한다. 이 검사는 화면 행동의 증거이며 실제 모델·공식 API 성공 증거는 위 실연동 기록 및 국내 추가 확인과 구분한다. Playwright를 제품 URL 수집기에 도입하지 않는다. 결과 원문·스크린샷과 독립 QA 결과는 실행 완료 후 아래에 추가한다.


### 실제 Chromium 화면 행동 검사 — 작성자 결과

Playwright 1.65.0 / Chromium 158.0.8127.18 headless에서 실제 React/Vite 화면을 실행했다. `cd frontend && npm run test:e2e`는 8 passed, 8 skipped였다. desktop 전용 7개 시나리오와 mobile 전용 1개 시나리오를 두 project에 정의하여 반대 project의 8개 조합을 건너뛴 것이며, 서로 다른 행동 시나리오는 총 8개다. `npm run build`도 통과했다. 제품 코드는 변경하지 않고 개발 테스트와 의존성만 추가했다. 독립 QA는 진행 중이다.

다섯 작업 상태를 각각 검사하고, 헤더 토큰·URL 미노출, 새로고침 후 세션 복구, 404 표시, 네트워크 오류 후 재조회, 늦은 응답을 수신하는 reset/abort 경주, HTML 문자열 escape·javascript 링크 거부·새 창 안전 속성, skip-link 키보드 초점·입력 label, 모바일 가로 넘침을 검사했다. API 응답은 모두 Playwright route fixture이며 실제 backend·모델·공식 API 호출을 수행하지 않았다. 이는 위 국내 실제 제품 연동 검사와 별개다.

화면 원문: `frontend/work/verification/desktop-report.png`, `frontend/work/verification/mobile-report.png`. 기존 `work/` 제외 규칙으로 버전 관리에서 제외한다. 자동 행동 검사와 스크린샷의 직접 시각 검토·독립 리뷰는 구분해 기록한다.


### 국내 독립 판매/제조사 원문 소규모 확인 — 실호출 결과

2026-11-09 원래 표본 3개를 시도했다. 제품 추천을 위한 선정이 아니라 서로 다른 국내 제품·제조사 원문을 확인하기 위한 편의 표본이다. 최초 sandbox DNS 실패 원문(`work/verification/2026-11-09-domestic-matching-sandbox-blocked.json`)과 승인 후 실제 수집·연동 원문(`work/verification/2026-11-09-domestic-matching-escalated.json`)을 구분해 보존했다. 모델 진입 조건이 브랜드를 포함한 전체 입력명을 요구해 KGC를 제외한 것을 보완한 후 KGC만 한 번 실행했다(`work/verification/2026-11-09-domestic-matching-kgc-only.json`). 락토핏 실모델 호출은 반복하지 않았다. 합계 유료 모델 호출은 2건이며 두 건 모두 구조화 추출을 완료했다.

| 독립 원문 제품 / 출처 식별자 | HTTPX 결과 | 실제 모델 추출 제품명 / 제조사 / 신고번호 | 공식 비교 결과 |
|---|---|---|---|
| 락토핏 골드 17포 / `ckdhc.com/product/productView.do`, 공개 상품 ID `CHC0000284` | 성공 | 락토핏 골드 17포 / 종근당건강(주) / null | unverified: 번호 누락으로 세 필드 동일성 미확인. 공식 일치 record 없음 |
| 고려은단 비타민C 1000 120정 / `ssg.com/item/itemView.ssg`, 공개 상품 ID `1000049983642` | http_error | 미호출 | 미평가 |
| 정관장 에브리타임 샷 / `jungkwanjang.kr/products/view.do`, 공개 상품 ID `1560` | 성공 | 에브리타임 샷 / ㈜한국인삼공사 / null | unverified: 번호 누락으로 세 필드 동일성 미확인. 공식 일치 record 없음 |

원래 표본 기준 수집 성공은 **2/3**, 실제 모델 추출 완료는 **2/2 호출**(원래 페이지 3개 중 2개), 제품명·제조사·신고번호 모두 확보는 **0/2 추출 완료**, 독립 공식 positive는 **0/3 원래 표본**이다. 두 successful 원문은 서로 다른 제조사이나, 제조사·제품명 표시는 등록 동일성의 확정 증거가 아니다. 공식 API의 전체 응답 row를 이번 하네스에 보관하지 않았으므로 official record 세 값의 별도 수동 대조는 미확인이다. 보고서 check의 unverified와 실제 공식 조회 호출 횟수도 구분한다. 번호를 공식 record로 채우거나 이미지/OCR/JavaScript 수집을 추가하지 않았다.

별도 대체 탐색의 올리브영 HTTP 오류와 CJ 페이지의 사이트명 한 줄/동적 정보 부족은 원래 3개 표본의 분모에 포함하지 않는다. 통제 negative는 모의 하네스 검사와 기존 실API 통제 검사로 구분한다. 이번 독립 원문에서 positive를 확보하지 못했으므로 **추가 입력 범위를 선택하기 전 당시 판정은 검사 실행 결과만 확보했으며 국내 매칭 품질 충분·M1 전체 완료 판정을 보류한다는 것이었다.** 이후 사용자가 선택한 추가 입력 M1 범위는 별도 완료 기준으로 검증하며 자동 매칭 성능의 한계는 유지한다. 추가 정보 입력을 M1으로 앞당기기·이미지 판독을 M1으로 앞당기기·현행 HTML 텍스트 범위 유지의 선택은 사용자 결정 후 다룬다. 하네스 독립 QA는 진행 중이다.


국내 최종 병합 evidence는 `work/verification/2026-11-09-domestic-matching-live.json`이다. 기존 실행과 KGC 단독 실행을 공개 상품 ID로 결합했고 latest KGC 행으로 이전 미호출 행을 대체한 provenance를 보존했다. 원래 표본 3개, 수집 2개, 추출 가능 텍스트 2개, 모델 시도/완료 2/2, 세 identity 확보 0개, 공식 check non-unavailable 2개, verified 0개다. `official_check_non_unavailable`는 보고서 check 집계이며 실제 API 요청 카운터라는 뜻이 아니다. 작성자 전용 검사 7 passed 및 Ruff 통과, 독립 QA는 이어서 진행한다.


### 화면 QA 지적 보완 — 작성자 2차 결과

초기 독립 QA가 발견한 필수 지적 2건(기존 5173 서버 재사용 가능성, 정상 토큰 reload 증거 누락)을 수정했다. Playwright는 전용 `127.0.0.1:5174`와 `--strictPort`, `reuseExistingServer: false`로 이 checkout의 Vite를 시작한다. 유효 토큰으로 queued→running→completed→새로고침 후 정상 보고서 복구를 검사하고, 잘못된 sessionStorage 토큰을 주입해 헤더에 따라 404로 분기하는 fixture로 오류 경로도 확인했다. 정상 보고서에 4종 check 상태, `500 mg`, `10 μg`, 함량·단위·기준 null 행을 추가했다.

작성자 재실행: `npm run test:e2e` **9 passed / 9 skipped / 0 failed** (서로 다른 행동 시나리오 9개, desktop/mobile project 선택으로 반대 조합 9개 skip), `npm run build` 및 diff whitespace 검사 통과. 정상 화면은 `frontend/work/verification/normal-desktop-report.png`, `frontend/work/verification/normal-mobile-report.png`, 보안 입력 화면은 `frontend/work/verification/security-desktop-report.png`로 구분했다. 실제 backend/모델/API 호출 없이 route fixture만 사용했다. 독립 QA 재확인은 진행 중이다.


### 추가 검증 독립 QA 최종 결과

`docs/reviews/m1-additional-review.md`에 작성자와 분리한 QA 결과와 소스 hash를 기록했다. Frontend 초기 필수 2건은 수정 후 해소됐고, QA가 전용 5174 서버에서 **9 passed / 9 skipped / 0 failed** 및 build 통과를 독립 재확인했다. 정상 desktop/mobile 캡처도 직접 확인했다. 국내 하네스 7 passed, Agent 19 passed 및 지정 Ruff 통과, 원문 JSON 4개 파싱·분모·provenance와 비밀값 미출력 경계를 검토했다. 병합 JSON 끝의 문자 그대로 `\n`은 작성자가 정상 재생성했고 QA 파싱 확인을 마쳤다. 추가 필수 소스 결함은 없었다. 실모델/API를 독립 QA에서 재호출하지 않았다. 독립 positive 0 및 공식 row 필드 미보관의 한계는 남는다.

사용자는 이 결과에서 부족한 정보를 한 묶음으로 입력하는 기능을 M1으로 앞당기기로 선택했다. 구현·재검증은 별도 새 루프이며 이 추가 검증 완료가 새 기능의 완료를 뜻하지 않는다.


## M1 추가 정보 입력 — 작성자 구현·독립 수정 루프

사용자는 추가 정보 1회 보완을 M1에 포함하기로 선택했다. 공유 계약은 `docs/contracts.md`에 있다. API/DB/Worker와 Agent, Frontend는 각각 다른 Luna 작성자가 구현했고 새 독립 QA를 실제 호출했다. 최초 QA 호출은 사용량 제한으로 실패하여 통과로 세지 않았으며, 사용자 재개 후 다시 검증했다.

- Backend 작성자: 관련 모의 33 passed/18 skipped, 실제 PostgreSQL 추가 입력 동시 수신 원자성 1 passed(SQLite parameter 1 skipped), Ruff 통과. 관련 누적 예산·시도/원문 파일 보존과 큐 발행 실패의 durable queued 경로를 검사했다.
- Agent 작성자: 일반 수집과 보완 graph, legacy report 누락 재계산과 snapshot 재사용 검사. 이후 독립 출처 회귀까지 합계 28 passed/Ruff였다. 실모델/API는 호출하지 않았다.
- 독립 QA는 예산 부족·예외 시 기존 보고서 유실, 선택 성분 공백 null 정규화 누락, 성분만/번호만 보완할 때 공식 대조 출처의 오표시를 재현했다. 담당 작성자가 수정했고 독립 회귀에서 해소를 확인했다. 마지막 사용자 보고서에 내부 필드명을 노출하는 한 줄 문구를 쉬운 표현으로 수정 중이며 최종 재검증 전이다. 실패 검사를 삭제하거나 완화하지 않았다.
- Frontend 작성자: 전용 5174 실제 Chromium **15 passed / 13 skipped / 0 failed**, build·diff 검사 통과. 28개 project 조합 중 desktop/mobile 양쪽의 보완 완료 흐름을 포함한 15개 실행이 통과했고 반대 project 전용 조합 13개는 의도한 skip이다. 모든 API는 route fixture이며 실서비스 모델·API는 호출하지 않았다.

입력 폼은 알고 있는 identity와 선택 성분을 한 묶음으로 제출하며, 수동 성분 목록이 기존 목록을 대체함을 제출 전에 설명한다. 선행 0 신고번호, `0005.00 mg`, `10 μg`, 함량·단위·기준 null을 변환하지 않는다. 202 후 폼 숨김/queued 재조회, used needs_input의 재입력 종료, 409·404·응답 유실 재조회, 새로고침 복원과 user_input 출처 표시를 브라우저로 검사했다.

원문 화면: `frontend/work/verification/supplement-desktop-form.png`, `supplement-mobile-form.png`, `supplement-desktop-report.png`, `supplement-mobile-report.png`. 루트가 desktop/mobile 폼과 결과를 직접 시각 확인하여 가로 잘림·겹침 없이 선택 단위/목록 대체/1회 입력/사용자 제공 표시/미확인 함량을 확인했다. 폼 캡처는 빈 제출을 검사한 뒤 값을 채운 시점이므로 초기 validation 문구가 남아 있다. 시각 확인도 실제 Chromium + mock API 경계다. 새 기능 독립 QA 최종판정과 실PG/Redis/Celery/I0030 통제 경로는 아직 대기다.


### 추가 입력 독립 QA 최종 판정

새 독립 QA가 필수 4건(실패 시 기존 보고서 보존, 선택 성분 공백 null, identity 실제 출처 citation, 사용자 안내 문구)을 모두 수정 후 재검증했다. `docs/reviews/m1-supplement-review.md`에 재현·수정 결과·검사 대상 SHA-256을 기록했다. 최종 관련 pytest는 **38 passed, 18 skipped**이며 skip은 실제 `TEST_DATABASE_URL` 미지정의 PostgreSQL 전용 검사다. 이는 작성자가 앞서 실제 PostgreSQL에서 수행한 추가 입력 동시 수신 원자성 1 pass와 구분한다. 관련 Ruff, 실제 Chromium **15 passed / 13 project skips**, TypeScript/Vite build를 독립 통과했다. 실모델/API는 QA에서 재호출하지 않았다.

최종 stdout/stderr 원문은 `work/verification/2026-11-09-supplement-qa-pytest.log`, `-ruff.log`, `-e2e.log`, `-build.log`에 있다. E2E 최초 sandbox 실행은 포트 bind 권한으로 실패했고 승인 후 재실행의 성공 로그를 보관했다. 초기 작성자/중간 QA 일부 검사는 별도 파일 로그 없이 도구 세션 출력과 요약만 보존됐으며, 최종 로그와 혼동하지 않는다. Root의 실제 통합 배포·통제 I0030 보완 경로는 다음 단계다.


### 실제 추가 입력 통합 경로 — 2026-11-09

최종 이미지 build 후 `docker compose up -d`로 API/Worker/Beat/Frontend와 migration을 반영했고 migration은 exit 0이었다. 루트가 `.venv/bin/python scripts/verify_supplement_live.py`를 실행해 exit 0을 확인했다. 원문은 `work/verification/2026-11-09-supplement-live.json`, 분석 ID `6eb751d1-8e4e-4f42-966f-b107ccded094`다. 조회 토큰과 키는 산출물에 보관하지 않았다.

실제 PostgreSQL에 명시적 통제 needs_input 보고서를 만든 뒤, 공식 record에서 가져온 세 identity를 **사용자 수동 보완 입력**으로 한 번 제출했다. POST202 → Redis/Celery → 실제 I0030 대조 verified → 본인 토큰 GET completed를 확인했다. 잘못된 토큰404, 두 번째 보완409, 최초 started_at 유지, attempt1→2, 누적 예약60→120초, 도구1→2를 확인해 사용자 대기 후 예산·시도 초기화가 없음을 검증했다. 사용자 제공 identity 세 필드의 출처와 수동 성분 source_id가 user-input이고 amount/unit/basis null이 그대로 유지됐다. `scope=collection_only`, `score=null`, `verdict=hold`, can_supplement=false다. 기존 수집/모델 호출은 추가하지 않았다.

초기 보고서는 test_fixture이고 수동 identity도 공식 record 유래이므로 이 성공은 **추가 정보 보완 경로의 실연동 통제 positive 1건**이다. 판매 페이지를 독립 수집·자동 식별한 국내 positive로 세지 않는다. 앞의 국내 자동 표본은 계속 3시도·2수집·신고번호 확보0·독립 positive0이며 HTML 텍스트 한계는 남는다. 등록 일치는 효과·실측 함량·개인 안전성 증명이 아니다. 독립 QA는 이 원문을 재호출 없이 대조 중이다.


독립 QA의 최종 live 원문 대조도 완료했다. verifier의 passed는 POST202 assertion을 포함하며(artifact에 status202 직접 필드는 없음), 원문의 completed·verified·404/409·누적 계수·시각·사용자 출처·null과 모델/수집0을 확인했다. 통제 input_type 및 independent_vendor_match=false를 유지했고 비밀값 패턴이 없음을 검토했다. script/task/Agent/독립 회귀 테스트의 최종 hash가 리뷰 표와 일치했다. 실제 API를 QA에서 다시 호출하지 않았다.


### 최종 실행본 동일성·readiness

`work/verification/2026-11-09-supplement-deployment.json`은 passed, API readiness의 database/broker 모두 true, Alembic revision은 `0002_m1_supplement`였다. API와 Worker의 Agent SHA-256은 검증 호스트의 `4400bf31ec5ffb1fa8f8837ec9ae03c721d7adea7533b742bcbc6aa4b0e81cb4`와 같았고 Frontend main/Report의 hash도 검증본과 일치했다. `runtime_matches_verified_source=true`를 확인했다. 전체 검증 소스 manifest는 `work/verification/2026-11-09-supplement-source.sha256`이며 키 파일은 포함하지 않는다.

따라서 합의된 M1 범위의 **권한 있는 추가 정보 1회 입력→예산 보존→실제 공식 재대조→조회/화면 출처 표시 경로와 이번 추가 검증 루프는 완료**했다. 이는 국내 자동 매칭 품질이 충분하다거나 전체 제품 평가가 완료됐다는 판정이 아니다. 자동 국내 표본 positive0, 통제 수동 보완 positive1을 구분해 유지한다. 사용자 선택 없이 이미지·회원·전체 평가로 범위를 확장하지 않았다.

### 사용자 질문에 따른 자동 매칭 진단 — 2026-11-09

추가 정보 보완 경로 통과와 URL만으로 하는 국내 자동 매칭 성공은 구분한다. 현재 `_check_official`은 페이지에서 추출한 제품명·제조사·신고번호가 모두 존재하고 세 값이 정확히 일치해야 verified로 판단하므로, 페이지에 신고번호가 없으면 공식 후보가 존재해도 확정할 수 없다.

실제 I0030에서 검색어 `에브리타임샷`은 `(주)한국인삼공사`의 `에브리타임샷`(20150002152119)과 `에브리타임샷스트롱`(20040020013449) 두 후보를 반환했다. 이는 미등록을 단정할 수 없다는 근거이며 판매 페이지와의 동일성을 확정한 증거는 아니다. 페이지 추출값은 `에브리타임 샷`/`㈜한국인삼공사`/번호 null이었다. 검색어의 표기 차이, 법인 표기 정규화, 페이지 신고번호 필수 조건을 별도로 검토해야 한다. `락토핏생유산균골드`라는 한 검색어는 0건이었으며 다른 등록명·제품 변형·검색 범위를 확인하지 않아 미등록으로 해석하지 않는다. 원문: `work/verification/2026-11-09-domestic-candidate-diagnosis.json`. 이번 조회는 AI 호출 없이 공식 API 후보 진단만 수행했다. 자동 후보 검색·다중 근거 대조의 개선 방향은 아직 사용자 선택 전이며 제품 코드를 변경하지 않았다.

## 자동 후보 대조 개선 진행 — 2026-11-09

추가 입력 구현 완료와 URL 자동 매칭 목표 달성을 분리해 작업을 재개했다. 공유 계약은 `docs/contracts.md`의 자동 공식 후보 대조 확장이다. 실API 원문 `work/verification/2026-11-09-official-candidate-evidence-fields.json`은 에브리타임샷 검색 total_count=2/rows=2와 샷·샷스트롱의 서로 다른 공식 기록을 보존한다. cached 독립 판매 페이지의 성분 목록과 API 원재료 전용 필드를 대조하며 API 값을 추출 입력에 넣지 않는다.

현재 작성자 backend/frontend와 새 독립 Luna QA를 분리했다. QA는 의미있는 제품명 문장부호·원료 괄호의 과도한 정규화, 불완전 metadata, 같은 성분·함량·단위 결합, 원문번호 없는 성공 설명, 보완 출처 정리·성분 출처를 검토한다. 필수 지적 수정·최종 독립 회귀·실API/실행 반영은 진행 중이므로 이 절은 완료 증거가 아니다.

### 현재 실API 결과와 완료 판정

`work/verification/2026-11-09-automatic-matching-cached.json`: 원래 3시도 중 독립 cached 원문추출 2건을 실제 I0030과 재대조했고, 1건은 기존 수집실패로 평가 제외했다. matched 0 / candidate 1 / unverified 1 / unknown 0이다. 새 모델 호출과 새 페이지 수집은 각각 0이다. 입력 baseline SHA256을 artifact에 보존했다.

에브리타임 샷은 띄어쓰기 유무 검색에서 이름·제조사와 독립 부원료가 일치하는 서로 다른 신고 기록 2건을 발견했다. 단일 후보가 아니므로 자동 확정을 보류하는 candidate가 정확한 결과다. 샷스트롱과 같은 제품으로 합치지 않는다. 락토핏은 공식 후보를 찾았지만 원문 `17포` 판매명과 공식 명칭의 동일성을 확정하지 못했다. 후보 검색 0을 미등록 증거로 해석하지 않는다.

따라서 **공식 후보 검색·보수적 대조·근거 표시 개선과 URL 자동 확정 목표 달성을 구분한다. 현재 실제 자동 positive는 0으로 원래 자동 확정 완료 기준은 미달이다.** 계약을 약화하거나 수동·통제·mock 성공으로 대체하지 않는다. 이후 마지막 신규 URL-only 전체 실검증과 배포 결과는 별도로 기록한다.

Frontend 작성자 검사: 전체 Chromium 16 passed/14 viewport skip 이후 양 viewport 신규 시나리오 2 passed, 독립 QA 전체 17 passed/13 viewport skip 및 production build 통과. 최종 화면 fixture의 번호 없는 matched 설명/확인내역 모순을 최소 수정한 후 해당 desktop/mobile 2 passed와 build를 다시 확인했다. 최종 캡처는 `frontend/work/verification/official-{candidate,matched}-{desktop,mobile}.png`다. 이 검사들은 route mock이며 실제 FDA·모델 품질 검증과 별개다.

### 최종 신규 URL 1회와 실행 반영

`work/verification/2026-11-09-automatic-matching-url.json`: 신규 비회원 URL-only 분석 `ccac979e-e335-4986-b5f5-aa8ed195b577`은 페이지 수집 verified였으나 모델 추출이 unavailable/request_failed로 끝나 제품명이 null이었고 공식 조회는 실행하지 못했다. 최종 needs_input이며 자동 경로의 성공을 입증하지 못했다. 토큰 없는 조회404/권한 조회200/추가 입력 미사용/점수 없음은 확인했다. 추가 모델 호출로 성공을 만들지 않았다.

현재 안전한 구현은 Compose에 반영했으며 readiness 및 migration0002를 확인했다. API/worker 구현 hash가 동일함을 root가 확인했다. 상세 실행 manifest는 최종 배포 artifact를 따른다. 이번 루프는 구현·필수 오류 수정·실패를 포함한 검증 결과를 기록해 종료하되 **국내 URL 자동 확정 목표가 달성됐다고 선언하지 않는다.**

## 2026-11-10 추출 실패 분류 최소 수정

마지막 URL의 15초 경과는 timeout 가설이지만 과거 request_failed 기록만으로 실제 원인을 확정할 수 없다. 새 작성자 Luna는 OpenAI typed 예외와 구조화 incomplete/refusal을 안전한 allowlist code로 구분하고 optional `extraction_status: {code}` 및 한국어 추출 확인 사유를 추가했다. 예외 문구·body·헤더·URL·키·토큰은 저장하거나 출력하지 않는다. SDK 자동 재시도0, 모델·출력/원문 한도·15초 외부/60초 시도/180초 활성·호출예산과 공식 매칭 조건은 유지하며 collection snapshot은 버전3이다.

작성자 관련 검사62 passed/Ruff/diff 통과. 새 독립 Luna QA의 관련 검사63 passed/Ruff/diff 통과, 필수 수정 지적0이다. 기존 supplement review의 source_ids exact 기대2건은 공식 후보 hash source가 추가된 계약을 반영해 원래 provenance 의미와 모든 출처 링크 실존 검사를 유지했다. [독립 리뷰](reviews/m1-extraction-diagnosis-review.md)에 정확한 명령과 범위를 기록했다. 이는 모의 검사이며 아직 새 실URL의 실패 원인을 입증하지 않는다. root는 분류 수정본 실행 반영 후 실URL1회를 진단하고 새 manifest를 남긴다.

이전 자동 매칭 실행 manifest는 `work/verification/2026-11-09-automatic-matching-deployment.json`으로 보존하며 이번 변경 실행본과 혼동하지 않는다.

추가 무생성 진단: `models.retrieve`는 host 약1.17초, worker container 약2.27초로 configured 모델 접근에 성공했다(root 실행). 이는 인증·모델 접근·기본 네트워크 연결을 확인하며 생성 요청의 15초 내 완료를 입증하지 않는다. Typed 실패 분류 수정본 배포 뒤 신규 KGC URL1회로 실제 분류를 확인한다. timeout이 확인되기 전에는 reasoning 옵션이나 시간상한을 바꾸지 않는다.

Typed 수정본 신규 URL 진단 `87eb2dea-e7e8-4e04-aec4-ea803dd8482c`에서 `extraction_status.code=timeout`, needs_input, 실모델1회/공식조회0을 확인했다. 원문은 `work/verification/2026-11-10-extraction-diagnosis-url.json`이다. 과거 일반 request_failed의 원인을 소급 확정하지 않으며 이 새 실행의 timeout만 확정한다. 후속 수정은 같은 모델·원문·15초 한도를 유지한 reasoning effort low 명시와 snapshot 버전 갱신에 한정한다. 아직 개선 효과는 미검증이다.

Reasoning low 최소 후속 수정은 작성자63 passed/Ruff/diff, 새 독립 QA73 passed/Ruff `--no-cache`/diff를 통과했다. QA 회귀는 collection v3 timeout snapshot을 버리고 v4 요청에 low만 전달하면서 기존 모델·원문·스키마·출력한도를 유지함을 확인했다. typed timeout의 unavailable/hold와 불완전 후보 보류 회귀도 유지된다. 실URL에서 속도·품질 개선 효과는 아직 미검증이다.

실행 반영 중 외부 환경 장애가 발생했다. host 저장공간 약81Mi로 Docker build I/O/read-only 오류가 났으며 root는 재다운로드 가능한 npm cache만 정리해 약2.1Gi를 확보하고 Docker 재시작·데이터 볼륨 상태 확인을 진행했다. 프로젝트·DB를 삭제하지 않았다. QA 최초 실행의 tempfile ENOSPC는 cache/capture를 끈 재실행으로73 passed, Ruff no-cache/diff 통과를 확인했다. 이 시점 low 수정본 실행 반영/실모델 호출은 아직 완료되지 않았다.

저장공간 장애 복구 결과: root는 멈춘 Docker backend 프로세스1개만 종료 후 Docker29.0.1을 재시작했고, 사용하지 않는 build cache16.53GB를 정리했다. 이미지·컨테이너·데이터 볼륨은 삭제하지 않았다. host free는 약81Mi에서19Gi로 회복했으며 기존 DB의 분석10행과 migration0002를 실제 조회해 보존을 확인했다. 최종 Compose build/up 뒤 low KGC1회와 별도 독립 ER Hana1회 검증을 수행하며 결과는 서로 다른 분모로 기록한다.

최종 build/up 후 low KGC URL-only 분석 `a5d12337-846f-4f52-b666-38d5ca13a6b7`은 `extraction_status=extracted`로 제품명 에브리타임샷·제조사 ㈜한국인삼공사·원문번호 null을 추출했다. 실제 I0030 2질의(반환3행/2행)에서 이름·제조사가 같은 서로 다른 신고2건으로 candidate/needs_input을 유지했다. 권한 없는404·권한 조회·추가 입력 미사용·점수 없음도 확인했다. 원문은 `work/verification/2026-11-10-low-kgc-url.json`이다. 이전 timeout 뒤 이 실행1건은 완료됐다는 관찰이며 일반 속도 개선률이나 자동 확정 성공으로 세지 않는다.

별도 독립 편의표본 ER Hana URL-only 분석 `b73b63bf-e1f0-4c5d-a4fd-c12b1514466a`은 low에서도 extraction timeout/공식조회0이었다. 원문은 `work/verification/2026-11-10-independent-seller-url.json`이다. 기존3제품 표본에 합치지 않으며 low가 일반 timeout 문제를 해결했다고 주장하지 않는다. 마지막 유한 수정은 같은 모델의 공식 지원 effort none과 collection snapshot5만 변경하고 같은 ER Hana URL1회로 확인한다.

마지막 none/v5 수정은 작성자63 passed/Ruff/diff, 독립 QA73 passed/Ruff no-cache/diff를 통과했다. v4 timeout snapshot 미재사용, none 옵션 전달과 기존 요청 내용·실행 한도 보존, 실패 시 timeout/unavailable/hold, 불완전 후보 candidate 유지를 확인했다. 필수 미해결 지적은 없다. 최종 none/v5 Compose build/up은 성공했으며 ER Hana 최종 URL1회 결과를 아래에 따로 기록한다. 테스트 통과만으로 효과·자동확정을 주장하지 않는다.

최종 none ER Hana URL-only 분석 `3d87d3ab-2bc8-4039-a99b-7f5e9151edd2`은 extraction extracted, 공식 번호1질의/1기록이었다. 판매 페이지에서 독립 추출한 이름 `ERr731® 여성 갱년기영양제`와 공식 이름 `이알하나 ERr731`이 달라 현행 엄격한 이름 계약에 따라 candidate로 남았다. 제조사 `(주)서흥`과 원문 표시 신고번호 `200400200062002`는 같지만 이것만으로 현재 이름 조건을 우회하지 않았다. 원문은 `work/verification/2026-11-10-none-independent-seller-url.json`이다. 예상 번호는 검증 assertion에만 쓰이며 접수·추출 입력에 주입하지 않았다.

이 표본은 기존3건과 별개인 추가 독립 판매 페이지 편의표본1건이다. low KGC와 none ER Hana가 각각 추출된 관찰을 일반 속도 개선률로 해석하지 않는다. **독립 자동 확정은 여전히0이다.** root는 번호·제조사·추가 성분이 같지만 이름이 다를 때의 동일성 규칙을 사용자 선택으로 확인 중이며 응답 전 매칭 코드를 변경하지 않는다. 현재 실행본은 none/v5의 보수적 candidate 판정을 유지한다.

실artifact 독립 read-only 대조 보충: KGC의 두 질의는 전체/반환이 각각3/3과2/2이며 보고서 후보는 dedup 후 총5건이다. 그 중 이름·제조사가 일치하는 신고2건 때문에 단일성을 확정하지 못한 것이며 전체 후보가2건이라는 뜻이 아니다. ER Hana의 최종 분석 상태는 `completed`이나 이는 collection_only 보고서 생성 완료다. official_match=candidate, matched_record=null, 검증 하네스=not_demonstrated이므로 제품 동일성 확정 완료와 구분한다. QA는 artifact 읽기만 수행했고 실콜·코드 변경을 하지 않았다.

최종 runtime 검증 `work/verification/2026-11-10-m1-deployment.json`은 passed다. API/worker/host의 collection_graph hash(`6f37e273…`)가 일치하고 frontend4파일도 일치하며 readiness DB/broker true, migration0002를 확인했다. 정확한 전체 hash는 `work/verification/2026-11-10-m1-source.sha256`에 보존한다. 실URL 결과와 배포 코드 일치를 확인한 것이며 자동 확정0이라는 제품 품질 결과를 바꾸지 않는다.

ER Hana의 독립 추출 성분과 공식 원재료를 기존 helper로 로컬 대조한 진단은 exact 부원료5개(이소말토올리고당·결정셀룰로스·해조칼슘·탄산칼슘혼합제제·목화씨앗유) match와 함량 missing2였다. 추가 외부 호출은0이며 같은 이름 조건을 우회하는 새 규칙을 적용한 결과가 아니다. 판매명과 등록명 차이를 다루는 사용자 선택은 여전히 대기한다.

## 사용자 승인 판매명 차이 경로 구현·검증 진행

번호·제조사와 모든 주요 기능성 원료를 대조하고 비교 가능한 함량/제형 모순이 없을 때 판매명 차이를 명시하는 새 경로를 구현 중이다. 기존 번호 없는 조건과 none·원문·실행 상한은 유지한다. 기존 ER Hana 독립 추출 wrapper로 실제 I0030을 재대조한 `2026-11-10-name-difference-cached.json`은 입력1/평가1/matched1/새 모델0이었다. 이 결과는 원문 추출을 재사용한 공식 실API 대조이며 신규 URL 전체 경로 성공과 구분한다.

새 독립 QA는 실제 `표시량(10㎍/1정)의80%~180%` 형식의 기준 파싱, 동일 성분 중복행 뒤의 충돌, 서로 다른 단위를 환산 없이 missing으로 처리하는 필수 회귀3건을 재현했다. 작성자가 최소 수정 중이며 아직 최종 성공·배포로 선언하지 않는다. Frontend는 내부 missing key의 한국어 라벨과 fixture 제품/공식 출처 정합 수정이 남아 있다. 원문/API값 역주입과 일반 부원료만으로 이름 차이를 확인하는 우회는 허용하지 않는다.

판매명 차이 새 규칙의 첫 신규 URL 분석 `ae75630f-8893-4b17-866d-cbd05ee66adf`은 추출 완료였으나 원재료9개만 뽑고 영양·기능정보표 D/K·함량을 누락해 candidate로 남았다(`2026-11-10-registration-match-url.json`). 이 부정 결과를 보존하고 무작위 동일 재시도를 하지 않는다. 기존 페이지에서 이미 제공된 필수 표도 추출하도록 시스템 지시를 최소 보완하고 collection snapshot7로 재검증한다. 원문/모델/none/스키마/15초/grounding/주요 원료 게이트는 변경하지 않는다.

판매명 차이 게이트의 필수 parser 수정본은 작성자+QA총60개, 독립 필수13개 회귀/Ruff/diff를 통과했다. UI의 내부 필드 라벨/공식 출처 fixture 및 실제 DTO 비교 누락 안내를 최소 정합 수정한 뒤 실제 Chromium desktop/mobile2개와 build·화면을 확인했다. 최종 캡처는 `frontend/work/verification/official-name-difference-{desktop,mobile}.png`다. UI는 mock 계약이며 첫 신규 URL의 candidate 결과를 positive로 대체하지 않는다.

표 추출 지시 최소 수정본은 작성자 및 기존 독립 게이트61개 회귀, 새 독립 최소 QA15개 회귀·Ruff·diff를 통과했다. [프롬프트 독립 리뷰](reviews/m1-registration-extraction-review.md)는 원재료/영양기능표 지시, 원산지와 섭취기준 구분, 상표/등록코드 보존 및 collection7의 이전6 재사용 방지를 확인했다. 스키마·모델·none·4,000 출력·15초·원문 grounding은 불변이다. 첫 신규 URL의9개 성분 누락 artifact는 변경 전 실패 기준으로 보존하며 실제 개선 효과는 다음 신규 URL 결과로만 판단한다.

두 번째 신규 URL 분석 `fe90bad8-94c9-4e2f-9500-1bb2ee350b4a`도 주요 원료 일부를 추출했으나 영양표 D/K 행 누락으로 candidate였다. 두 신규 실행의 누락 부정 결과를 모두 보존하며 반복 호출로 positive를 만들지 않는다. 원문은16,617자로24,000자 한도에 잘린 사례가 아니고 영양표에 U+338D `㎍` 단위가 있다. 모델 excerpt의 단위 타이포그래피와 strict excerpt grounding 간 불일치 가능성은 아직 가설이다. 제품 grounding을 약화하지 않고 진단 하네스에서 원시 구조화 추출과 grounding 전후 탈락 사유를 관찰해야 원인을 구분할 수 있다.
# 최종 M1 마감 증거 — 2026-11-10

최신 결과는 [M1 마감](m1-closeout.md)과 `work/verification/2026-11-10-m1-structured-final-url.json`이다. 새 URL-only 실제 수집·표 직접 읽기(모델0)·실I0030·DB 저장·권한 조회가 passed/10개 검사true였다. 이전 모델 표 누락2건/timeout2건은 보존한다. 새 독립 QA 관련93회귀·Ruff·diff, 관련 실제 Chromium2개(mock API)·build·시각 확인 통과. 실행본 동일성/readiness/migration은 `2026-11-10-m1-closeout-deployment.json`, 소스 manifest는 `2026-11-10-m1-closeout-source.sha256`이다. 아래 내용은 누적 실험 이력이며 최종 범위와 한계는 마감 문서를 따른다.


## 고정20개 평가 Stage0

`work/verification/2026-11-10-m1-evaluation-stage0.json`은 고정20개/5사이트를 처리했다. HTML16개, SSG HTTP오류4개, structured_page1개, 모델 요청0·공식 요청0이다. 생성시각2026-11-10T16:06:41Z/run13865549aec54c29/hashcd86ffd…는 원본 그대로 보존한다. 이는 모델·공식 대조 품질 평가 완료가 아니며 실패4개도 분모20에 남긴다. Stage1 전 raw16개를 독립 관찰해 같은20URL의 라벨 v2를 freeze하고 별도 출력으로 모델/API를 측정한다. 후속 하네스는 공식 정답 known/unknown과 판정 outcome 분모를 분리하고 구조화 추출 소스 hash·비밀 제외 실행 설정을 서명에 추가한다. Stage0은 재실행하지 않는다.

Stage1 전 하네스 최종 독립 QA는 작성자+독립31개 회귀·Ruff·help·diff를 통과했다. 독립19개는 v1/v2의 같은20URL·parent hash·정확 라벨 분포, 필드별 label_status와 outcome 분모 분리, 추출 미완료 unjudged/성공 시 expected_missing·unexpected_present, 실제 matched_record 번호 판정, metadata 비주입, atomic resume·설정 불일치 거부·구조화 추출 소스 hash·비기밀 설정만의 실행 서명을 확인했다. [평가 리뷰](reviews/m1-evaluation-review.md)에 초기 지적과 수정 후 결과를 기록했다. QA 외부 호출은0이다.

Stage1은 root가 `m1-corpus-annotated-v2.json`과 별도 `work/verification/2026-11-11-m1-evaluation-stage1.json`으로 실행 중이다. 완료 결과의 matched 전건은 독립 읽기 전용 사후 판정을 따로 남긴다. 이때 원래 unknown 정답 라벨을 사후 gold로 바꾸거나 최초 성능 분모를 덮지 않는다.

## 마지막 identity guard와 배포 회귀

마지막 수정은 ML identity placeholder 보류와 명시 제조 역할·같은 회사의 표 행/문단 결합 검증2개다. strict 직접 표 parser는 그대로이며 collection snapshot10이다. 제품 graph SHA256은 `b3f33cf6596b37ab14f48961ada5427ee4168542bb651a9038ff8dcf50b9f429`; 작성자 관련81개 회귀·Ruff·diff를 통과했다. 원20개 baseline은 재실행하거나 고치지 않았다.

`work/verification/2026-11-11-identity-guard-replay.json`은 별도 오프라인 helper 검사다. 원문 cache와5개 알려진 제조사 값을 검사해 유지하고 GS 여성팩 placeholder와 ER56 footer제조사 값을 보류했다. KGC387은 baseline 모델이 놓친 known 라벨 값을 이용한 synthetic 역할 검사이며 모델 추출 복구 성공으로 세지 않는다. 원래 모델 excerpt가 없어 전체 추출 재생이라고 주장하지 않는다. 외부 모델·API 호출은0이다.

root 최종 배포 URL-only 회귀 `87a506f5-63af-4be2-8773-cd3224457ab0`은 `2026-11-11-m1-guard-final-url.json`에서10/10 passed였다. 실제 URL 접수→structured_page(모델0)→공식 matched/판매명 차이 공개→DB completed·원문 저장·권한 조회를 확인했다. 무토큰404/수동 입력0, attempt1/활성예약60초/tool2/snapshot10/migration0002와 ready200 DB·broker true를 확인했다. host/API/worker graph·parser·config3개 hash가 일치하며 배포 evidence는 `2026-11-11-m1-guard-deployment.json`이다. 이 후속1건은 원baseline20개 결과와 별도이며 일반 정확도 보증으로 확대하지 않는다. 마지막 guard 독립 QA 후 최종 M2 게이트를 닫는다.

최종 guard 독립 QA는9개 회귀·Ruff·diff를 통과했고 graph/parser hash 및 오프라인 replay cache hash·무호출 기록을 확인했다. [독립 리뷰](reviews/m1-identity-guard-review.md)에 필수 지적 없음과 M2 보류를 분리해 기록했다. 원20개 baseline은 불변이며 수정 후 전체 성능 재측정으로 세지 않는다. M1 한정 점검·배포 회귀·결과 기록은 마쳤고 **M2는 사용자 지시로 보류·미진입**이다.

## 2026-11-11 M2-A Task1 근거 도구

Superpowers TDD/독립 검토 루프의 Task1을 마쳤다. DOI 정규화, malformed JSON 안전 오류, quote ID 고유성의 독립 지적3건을 작성자가 수정했고 동일 검증자의 scoped 재검토에서 모두 ADDRESSED, spec ✅ / quality Approved였다. 리드는 수정 후 `.venv/bin/python -m pytest -q --tb=short`를 실행해 **269 passed,19 skipped (5.21s)**를 확인했다. PostgreSQL 선택 검사 등19개는 건너뛰었으며 PG/실제 모델·검색 연동 통과를 뜻하지 않는다. 이번 새 도구의 외부 서비스 요청은0이다. 상세 TDD/관련 Ruff/파일 hash는 `work/verification/m2a/task-1-report.md`, 독립 결과는 `task-1-rereview.md`, 리드 최종 hash와 전체 suite 결과는 `task-1-verified.json`에 있다. Task2 조사 그래프와 API/Worker/UI 연결은 아직 진행 중이다.

## 2026-11-11 M2-A Task2 조사 그래프

실제 LangGraph Supervisor/전문역할 제어를 구현하고 독립 검토에서 발견한 필수6항을 수정했다. lease상실후요청차단,결과·source와in-flight해제동일저장,yield후재개,모델timeout일치,공유state잠금,TDD증거를scoped재검토했다. 초기RED는import실패였다는한계를유지하며,fix1은실제동작회귀5failed→5passed를관찰했다. 지정모의회귀107passed(2.30s),Ruff통과. 독립spec✅/qualityApproved. 근거는`work/verification/m2a/task-2-report.md`, `task-2-rereview.md`,fixdiff와hash다. 실제Worker/DBfencing과외부모델·검색API검증은아직수행하지않았고Task3이후다룬다.

## 2026-11-11 M2-A Task3 DB·Worker·API

mode기본collection/명시evidence_review,0003migration,권한조회,fencedyield와M1보존/연구재개를구현했다. 독립초기검토의research_started우려는brief의보수적failclosed정책과대조해철회됐고spec✅/qualityApproved로정정했다. 리드추가DTO누락을fix1에서수정했고새usage.total0회귀는fix2에서실DB누적total/역할귀속unknown으로수정했다. 실제RED각1→GREEN각1,수정후관련42passed/18PGskips,Ruff통과,독립scoped재검토spec✅/qualityApproved. 증거:work/verification/m2a/task-3-report.md와task-3-initial-review.md/task-3-rereview.md.

리드가실PG TEST_DATABASE_URL로전체suite를실행했다. 최초sandboxTCP차단으로303passed/3skips/16PGsetup-errors였으며승인escalation재실행은**319passed/3skipped(8.86s)**였다. 이실PG전체결과는DTO/usage보완전소스이므로최종수정후전체회귀는Task5에서다시검증한다. 기존PGfixture의UUIDschema격리/0003head migration/경쟁예약을검사했고새M2yield실PG검사는Task5에남는다. 실행중publicDB는0002/분석19건(완료6/정보부족13),검사전후유지됐다. 새제품모델/자료API호출과실배포는아직0이다.

## M2-A 화면 Task4 검증

실제 UI 행동 RED를 먼저 관찰한 뒤 조사 선택·역할 결과·출처 화면을 구현했다. 독립 검토에서 상태·범위·footer와 정상 기초 보고서 상세 누락을 수정했다. 기존 Report를 native details에서 재사용하고, 선택 필드 report_number가 생략된 과거 보고서 호환도 보완했다. 최종 독립 scoped 판정은 Spec✅/Quality Approved다.

fix1 전체 Chromium은25passed/21project-filter skips와build통과,fix2는실제UI RED1→관련3passed/3filtered skips와build통과다. 375px·landscape·reduced-motion·125%텍스트검사와desktop/mobile PNG를확인했다. 모두API fixture이며실API/외부자료연동검증이아니다. 자세한명령·hash는`work/verification/m2a/task-4-report.md`,독립결과는`task-4-rereview.md`다.

## 최종 사용자 A 선택 — 필수 수정 후 제한 마감

주간 한도에 따라 로컬 배포·실제 URL 실행을 다음 한도로 이관한다. 최종 전체 candidate 검사는 실PG342 passed/4 skipped, Chromium fixture26 passed/22 filtered skips, Ruff 통과였다. 이 결과 뒤 최종 독립 검토에서 두 필수 문제를 발견했다.

일반 공식 원료 자료의 product_applicable 통과와 M2 초기 HTTP 요청의 durable 표식 누락을 수정했다. 실제 동작 RED2를 먼저 관찰했고, 수정 후 지정 관련 검사는 **90 passed/5 PostgreSQL 조건 skips**, 담당 Ruff 통과다. 이 마지막 수정본의 실PG 전체 회귀는 아직 실행하지 않았다. 앞선342 통과를 마지막 수정본의 전체 통과로 주장하지 않는다.

증거는 `work/verification/m2a/final-fix-report.md`, 원본 바이트 비교 `final-fix-review.diff`, 마지막 소스 `checkpoint-source-sha256.json`, 범위·미검증 `closure-verification.json`이다. 최종 scoped 독립 재검토 결과는 [리뷰 기록](reviews/m2a-review.md)에 추가한다. 서비스 반영·실행본 hash·실제 provider 결과는 아직 미검증이다. 준비한 Docker 이미지는 마지막 두 수정 전 버전이므로 다음 반영 때 재빌드해야 한다.

### 제한 마감의 최종 확인

독립 검토자 `m2a_final_review`가 필수 두 수정과 중단 보고서 카운터 회귀를 모두 ADDRESSED로 확인했고 scoped quality Approved를 보고했다. 마지막 정정은 대상 테스트1 passed와 담당 Ruff 통과이며, 같은 worker 오류·재시작 복원 모두 DB 예약 총계가 보존된다. 최신 소스는 checkpoint-source-sha256.json이다. 전체 실PG342/4skip는 수정 전 candidate 기록이며, 마지막 수정 후 전체 실PG 검증은 다음 작업이다. 실행 서비스는 이번에 변경하지 않았고 실제 제품 URL/provider 요청은0건이다.
