# M1 추가 독립 QA — Frontend

기준본: `/Users/hyeonseokbae/Desktop/ad_fact_check`, 2026-11-09. 소스 검토와 검증 실행을 구현 담당자와 분리해 수행했다. Frontend 소스, API 호출 흐름, M1 HTTP 계약과 검증 계획을 함께 확인했다. 제품 실서비스 모델/API는 호출하지 않았으며 E2E의 모든 API 응답은 Playwright route fixture다.

## 판정

**초기 필수 지적 2건은 구현자가 수정했고 독립 재검증에서 해소됐다.** 전용 포트에서 18개 브라우저 테스트 중 9 passed/9 skipped, build 통과를 확인했다. 추가로 국내 매칭 하네스와 생성 증거를 오프라인 검토했다. 국내 live sample에서 완전한 세 필드 identity 0/3, 공식 verified 0/2였으며 공식 응답 row가 보존되지 않아 공식 필드별 비교는 미검증이다. 이는 실행 검증 완료이지 매칭 품질 충분 판정이 아니다.

### 1차 필수 지적 (수정 후 해소)

1. **테스트가 실행 중인 Vite/Docker 서버를 재사용할 수 있음** — `frontend/playwright.config.ts:20-27`
   - 재현: `CI`가 아닌 로컬에서 Playwright를 실행하는 동안 5173 포트에 이전 Vite 또는 Docker frontend가 응답하면 `reuseExistingServer: true`가 그 서버를 재사용한다. 이때 소스와 다른 UI에 대해 테스트가 통과할 수 있다. `vite.config.ts`도 5173을 사용한다.
   - 영향: 현재 테스트 결과와 screenshot이 이번 변경 소스에서 생성됐다는 증거가 보장되지 않는다.
   - 최소 수정: Playwright 전용 포트(5174)를 `strictPort: true`로 실행하고 `reuseExistingServer: false`로 설정한다. **수정 확인:** `playwright.config.ts:9, 18-22`가 전용 5174에서 이를 적용한다.

2. **세션 복원 테스트가 유효한 재조회/토큰 전송을 검증하지 않음** — `frontend/e2e/analysis.spec.ts:81-93`
   - 재현: 현재 route는 제출 전후 조회를 모두 404로 돌려준다. reload 이후 실제 조회 헤더를 기록하거나 기대하지 않고 sessionStorage에 토큰 문자열이 있다는 것만 확인한다.
   - 영향: 잘못된 토큰과 올바른 토큰의 동일 404 응답을 검사한다고 테스트 이름은 말하지만, 잘못된 토큰 요청도 없고 유효 토큰으로 복원된 결과도 확인하지 않는다. 저장 후 reload 복구 회귀를 놓칠 수 있다.
   - 최소 수정: 유효 토큰으로 조회하는 route에서 reload 뒤 `X-Analysis-Token`을 검사하고 정상 상태/보고서가 복원되는 것을 확인한다. 별도의 잘못된 토큰 route도 추가해 UI 오류가 동일한지 확인한다. **수정 확인:** `analysis.spec.ts:102-117, 119-149`에 잘못된 토큰 404와 queued→running→completed, reload 후 유효 토큰 헤더/보고서 확인이 추가됐다.

### 권장 보완

1. **정상 보고서의 필드/단위 표본이 없음** — `frontend/e2e/analysis.spec.ts:14-24, 57-75`
   - 1차 리뷰 당시 보고서 fixture는 `checks`와 `ingredients`가 빈 배열이었다. 테스트는 HTML injection·악성 URL 안전성을 검증하지만 정상 확인 내역, `mg`/`μg`, 함량 null을 렌더하는 경로는 밟지 않았다.
   - 최소 수정: 별도 정상 fixture에 check 상태들과 함량 값·단위 및 null 값을 포함하고, 각각의 표시와 추정값 부재를 확인한다. 표본 통과율을 산출하는 국내 제품/API 검증과 혼동하지 않는다.

2. **화면 캡처는 악성 입력 fixture 한 종류만 담음** — `frontend/e2e/analysis.spec.ts:77, 136`
   - 1차 리뷰 시점 두 screenshot 모두 완료 보고서에 테스트용 XSS 문자열과 출처를 표시했다. 모바일 폭 초과 검사는 통과했지만 실제 정상 보고서 화면의 시각 검증 자료는 아니었다.
   - 최소 수정: 정상 fixture에 대한 desktop/mobile screenshot을 추가한다. 악성 fixture 캡처는 보안 동작 증거로 구분해 보존한다.

## 검토 결과

- `Report.tsx`는 요약·문구·excerpt/title을 React 텍스트 노드로 렌더링하며 HTML 삽입을 하지 않는다. source URL은 `http:`/`https:`만 링크로 만들고 사용자정보가 있는 URL을 제외한다. 외부 링크에 `noopener noreferrer` 및 `no-referrer`를 설정한다.
- `main.tsx`는 URL protocol을 http/https로 제한한다. 조회 토큰은 URL이 아닌 `X-Analysis-Token` 헤더로 보내고 `sessionStorage`에만 저장한다. 분석 handle을 검증하며 제출/조회에 AbortController timeout과 cleanup abort, 제출 sequence guard 및 조회 effect active guard가 있다. Reset 이후 늦은 조회 응답을 무시하는 브라우저 시나리오는 통과했다.
- 1차 기준에서 요구된 상태 라벨 5종(queued/running/needs_input/completed/failed)의 rendering mock 시나리오는 존재했다. 당시 상태 테스트 assertion은 label과 status 요청 header를 확인했으며 각 상태 payload 정합성은 약하게 확인했다. 수정본에서는 별도 queued→running→completed 진행과 정상 보고서 표시를 검증한다.
- 모바일 Chromium에서 완료 화면을 실제 렌더하고 `scrollWidth <= innerWidth`를 통과했다. screenshot은 수동 확인했으며 폭 초과·레이아웃 겹침은 관찰하지 않았다. desktop/mobile 모두 screenshot 파일을 생성했다.
- `package.json`의 `build`/`test:e2e` scripts와 설치된 Playwright 사용은 단순하다. `package-lock.json` 포함은 재현 가능한 설치에 적절하다. 이번 QA에서는 잠금파일을 변경하지 않았고 `npm ci`는 수행하지 않았다.

## 검증 증거

- 1차 최초 sandbox 실행은 Vite의 `127.0.0.1:5173` bind에서 `EPERM`으로 실패했다. localhost listener 권한 승인 뒤 실행했다.
- 1차 `cd frontend && npm run test:e2e`: 실제 Chromium, mock API. **16 total: 8 passed, 8 skipped**, 0 failed. 7 desktop 동작 시나리오와 1 mobile 시나리오가 실행됐다. 프로젝트 간 skip은 각 테스트가 대상 브라우저 프로젝트만 실행하도록 한 결과다.
- 1차 `cd frontend && npm run build`: TypeScript 검사 및 Vite 7.3.7 production build 통과.
- Screenshot: `frontend/work/verification/desktop-report.png`, `frontend/work/verification/mobile-report.png` (테스트 XSS fixture 기준; 정상 보고서 UI 증거가 아님).
- 검증 대상 SHA-256:

```text
frontend/package.json                 51fa3d18bde890fad4433cf1a531c696152ebb2797b707fe8fe619221deacd36
frontend/package-lock.json             d03c7ce368a36d357b7b3238c99131802079ba45370209c2418f4980ecac170d
frontend/playwright.config.ts          ca880025fe68467f7a23fa1ba764babc0bae065adfb6796138841b6cf7aea6e0
frontend/e2e/analysis.spec.ts           2b50012bfec96cb08e76a59b5bff74e68a26b6622cdbab4d55bb3d1e3b57d1ba
frontend/src/main.tsx                  16f02a9b224bbebf479680170023112797b631f9f5c1af734889edb1c5b9ae29
frontend/src/Report.tsx                7a6131af20af246c66fcf89edad82484f5f44f847557423c37f93a4afc7baf3b
frontend/src/types.ts                  bb51ee112535867c282e360f775f2d358d42632ef271adfadfdd24c8dbc36430
```

## 1차 범위 한계

API fixture 기반 UI 검사이므로 실제 backend/API, 모델 호출, FoodSafety 응답, 제품 품질을 검증하지 않는다. mobile은 Playwright iPhone 13 Chromium emulation이다. 실제 iPhone Safari/기기 및 screen reader는 검사하지 않았다. 당시 정상 mg/μg/null 렌더, 유효 토큰 reload, 전용 서버 재검증이 남아 있었다(아래 재검증 참조).

## 수정본 Frontend 재검증 — 2026-11-09

- `cd frontend && npm run test:e2e`: Playwright 전용 `127.0.0.1:5174`, `strictPort`, `reuseExistingServer: false`; 실제 Chromium, 모든 API 응답은 route fixture. **18 total: 9 passed, 9 skipped**, 0 failed. 8 desktop 동작/보안 시나리오와 1 mobile 시나리오 실행, 프로젝트별 의도 skip 9건.
- 새 시나리오에서 invalid token은 404 UI를 표시했고, 정상 세션은 queued→running→completed 후 reload 때 `X-Analysis-Token`이 유지되고 보고서를 복원했다. 확인 내역 네 상태, 500 mg, 10 μg, null 함량(`함량 미확인`)을 렌더했다.
- `cd frontend && npm run build`: TypeScript 검사 및 Vite 7.3.7 production build 통과.
- 정상 screenshot을 실제 파일로 확인했고 mobile 가로 overflow가 없었다: `frontend/work/verification/normal-desktop-report.png`, `frontend/work/verification/normal-mobile-report.png`. XSS fixture용 캡처는 `security-desktop-report.png`로 구분됐다. 실제 iPhone Safari/device 테스트는 하지 않았다.
- 수정본 hash:

```text
frontend/playwright.config.ts          ee0f9e5c3ba61331fbabb13fb18832f59b7e24049d2dd1145456e57c00d0c92f
frontend/e2e/analysis.spec.ts           53c118c5f60ec84f95a5170fb745d9d18feb567a08d55813d3629391552ee689
```

## 국내 제품 매칭 하네스 독립 QA — 2026-11-09

### 소스/정책 검토

- `scripts/verify_domestic_matching.py`는 키 없는 기본 모드와 explicit opt-in을 분리하며 제품 표본은 공개 ID로 제한 가능하다. `_safe_url`은 query/fragment/userinfo를 산출물에서 제거한다. 수집 실패·페이지 텍스트 부족도 시도/수집 분모에 남기고, 부족한 페이지는 그래프·모델에 보내지 않는다. 실모델/API 재실행은 하지 않았다.
- Merge는 old schema `identity_information_sufficient_for_extraction`을 새 `identity_page_text_eligible_for_extraction`으로 정규화하고, `source_url`의 public product ID를 join key로 복원한다. 해당 구형 필드와 product ID가 없는 row를 URL query에서 복원하는 offline regression이 있다. 소스 리뷰에서 추가 필수 결함은 발견하지 않았다.
- `CONTROL_CATEGORIES`는 `wrong_manufacturer`, `missing_report_number`, `insufficient_identity`라는 명칭을 적어둔 목록이다. 이것은 통제 시나리오를 실행했다는 기록이 아니며, 별도 통제 실행 수는 0이다. live 표본/분모에 통제 결과를 더하지 않았다.
- `tests/test_domestic_matching_harness.py`는 개인정보/쿼리값 제거, 추출 전 텍스트 gate, 실패/부족 분모 유지, merge provenance를 확인한다. 지정 파일 Clean Code/Ruff 오류는 없었다.

### Evidence 분모 및 한계

- 작성자가 처음 만든 merged `2026-11-09-domestic-matching-live.json`은 끝에 literal `\\n`이 붙어 `json.loads`가 실패했다. 이를 작성자에게 보고했고, 작성자가 재생성한 뒤 최종 산출물을 다시 파싱해 정상 JSON임을 확인했다. `-escalated.json`, `-kgc-only.json`, `-sandbox-blocked.json`도 모두 JSON 파싱에 성공했다.
- 최종 merged live 산출물은 3개 고유 제품(ID `CHC0000284`, `1000049983642`, `1560`)을 보존한다. 시도 3, collection 성공 2, page-text 추출 eligibility 2, 이름·제조사·신고번호가 모두 있는 identity 0, model call attempted/completed 2/2, official check non-unavailable 2, `verified` 0이다. 락토핏/정관장 각 1회 모델 호출은 usable extraction으로 완료됐지만 둘 다 신고번호가 없어 complete identity가 아니며 official check는 `unverified`; SSG 제품은 collection 실패했다.
- 공식 API 응답 row/필드값은 산출물에 보관되지 않았고 graph도 non-match의 row 필드값을 report source로 내보내지 않는다. 따라서 공식값과 판매페이지 추출값의 name/manufacturer/report-number별 대조는 미검증이다. 이 표본은 국내 official positive가 없고 매칭 품질 충분 여부를 판정하지 않는다.
- `-sandbox-blocked.json`은 3개 수집 전부 실패, 모델/official call 0건으로 외부 호출 차단 실행 증거일 뿐 matching sample이 아니다.
- 네 evidence 파일에서 credential/token/authorization 등 비밀 필드명은 발견하지 않았다. 증거 JSON의 API key/token 값 노출은 확인되지 않았다.

### 오프라인 검증 및 소스 hash

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_domestic_matching_harness.py -q`: **7 passed**.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_agents.py -q`: **19 passed**.
- `.venv/bin/ruff check scripts/verify_domestic_matching.py tests/test_domestic_matching_harness.py src/supplement_advisor/agents/collection_graph.py`: 통과.
- 실모델/API는 재실행하지 않았다. 이는 사용자 승인된 두 live call(락토핏 1, KGC 1)의 산출물에 대한 독립 검토다.

```text
scripts/verify_domestic_matching.py                  f4f39cdfc2c0974c837b980e8fc6f495bb82ecf6d8ca5f26d1dafedd6b4c3e08
tests/test_domestic_matching_harness.py              79362df06618d6b4d38e29372f17ebea5a4e31eb6fef15cd9f96446f82f1b0e8
src/supplement_advisor/agents/collection_graph.py    60c85a7cb98c97a09a77dcd36a8e71063fcd9c38e678d12a83dcc3a32b5cb147
```
