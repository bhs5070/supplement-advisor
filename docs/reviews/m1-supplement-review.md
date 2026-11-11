# M1 추가 정보 입력 독립 QA — 최종 모의·브라우저 판정

작성자와 분리해 backend, Agent, Frontend 변경을 검토했다. 아래 필수 수정 4건은 모두 수정 후 독립 회귀 검사에서 해소됐다. Frontend mock e2e/build와 desktop/mobile screenshot을 확인했다. 실제 DB/공식 API live script는 실행하지 않았다. 실모델·공식 API 추가 호출은 하지 않았다.

## 필수 수정

### 1. 추가 입력 처리 실패가 기존 보고서를 삭제함

- 위치: `src/supplement_advisor/tasks.py`의 `execute_analysis`, 상태 초기화 및 `finish_analysis` 호출 (현재 대략 60행 및 125행).
- 재현: `tests/test_supplement_review.py::test_supplement_budget_exhaustion_preserves_existing_report`. needs_input 보고서를 저장하고 `active_seconds_reserved=150`으로 둔 뒤 추가 정보를 제출했다. 180초 누적 한도에서 60초 추가 예약이 거부되어 `failed/budget_exhausted`가 기록됐고, 이전 보고서는 DB에서 `NULL`로 바뀌었다. 검사 결과 실패를 확인했다.
- 영향: 재대조 예산이 없거나 보완 그래프가 예외로 끝나도 이전 수집 보고서와 근거를 GET에서 복구할 수 없게 된다. 이는 추가 입력 전 저장된 보고서를 보존해야 하는 계약의 데이터 보존 의도와 충돌한다.
- 최소 수정: supplement 경로에서 새 보고서를 만들지 못한 경우 `stored_report`를 `finish_analysis`에 전달해 기존 보고서를 보존한다. 일반 최초 수집 실패의 응답 의미는 불필요하게 바꾸지 않는다.

### 2. 공백뿐인 선택 성분 값이 빈 문자열로 저장됨

- 위치: `src/supplement_advisor/schemas.py`의 `SupplementalIngredient.strip_values` (현재 대략 55행).
- 재현: `tests/test_supplement_review.py::test_blank_optional_ingredient_values_normalize_to_null`에서 `amount=" "`, `unit="\t"`, `basis="  "`를 입력했다. 정리 뒤 세 값이 `None`이 아니라 `""`로 남아 검사가 실패했다.
- 영향: 사용자가 값을 제공하지 않은 성분 필드가 null 대신 빈 문자열로 API/Agent 보고서에 전달되며, 화면이나 downstream 소비자가 이를 입력값으로 다르게 표시·해석할 수 있다. 계약은 값이 없는 함량·단위·기준을 추정하지 않고 null로 보존하도록 한다.
- 최소 수정: optional ingredient field는 trim 후 빈 문자열을 `None`으로 정규화한다. `name`은 현재처럼 공백 입력을 거부한다.

### 3. 공식 대조 설명과 출처가 사용자가 보완한 identity field에 맞지 않음

- 위치: `src/supplement_advisor/agents/collection_graph.py`의 추가 대조 report node, `field_sources` 생성 이후 official check 작성부 (현재 대략 566–594행).
- 재현: `tests/test_supplement_review.py::test_ingredients_only_supplement_does_not_claim_identity_was_user_provided` 및 `test_report_number_only_supplement_cites_page_and_user_identity_sources`가 ingredients-only / report-number-only 입력으로 공식 응답을 mock했다. 최초에는 각각 detail과 source id가 실제 provenance를 반영하지 않아 실패했다. 수정 후 두 검사와 해당 Agent 테스트가 통과했다.
- 영향: 공식 동일성 확인의 근거가 실제로 어떤 정보였는지 보고서가 잘못 설명하거나 일부 출처를 누락한다. 성분만 입력했는데 identity를 사용자 입력으로 오인하게 하거나, 판매 페이지의 이름·제조사가 공식 대조에 쓰였다는 근거를 감춘다.
- 최소 수정: `field_sources`의 실제 source id를 기준으로 공식 check의 `source_ids`를 구성한다(제품 페이지/user-input/official-i0030). 안내 문구도 수집 정보와 사용자 보완 정보 중 표시된 출처를 사용해 대조했음을 밝히고, 사용자 입력만으로 대조했다고 단정하지 않는다. **수정 확인:** 현재 source_ids/detail은 실제 identity provenance를 따른다.

### 4. 보고서 limitation에 내부 field 이름 노출

- 위치: `src/supplement_advisor/agents/collection_graph.py`의 추가 입력 보고서 limitation (현재 대략 617행).
- 재현: `tests/test_supplement_review.py::test_report_limitation_does_not_expose_implementation_field_names`에서 사용자 입력을 반영한 보고서 limitation에 `product.field_sources`와 `source_id`가 그대로 나타남을 확인했다. 최초 검사가 실패했으며 수정 후 통과했다.
- 영향: 소비자 보고서가 앱 내부 자료구조 이름을 보여 주어 이해가 어렵고 사용자에게 불필요한 구현 정보를 노출한다.
- 최소 수정: “사용자가 보완한 항목에는 사용자 추가 입력이라고 표시했습니다. 개인 적합성은 평가하지 않았습니다.”처럼 출처 표시를 평이한 말로 안내한다.
- **수정 확인:** 제한 문구가 사용자에게 읽기 쉬운 문장으로 바뀌었고 회귀 검사가 통과했다.

## 실행한 검사

- `.venv/bin/python -m pytest tests/test_supplement_review.py tests/test_supplement_backend.py tests/test_supplement_agents.py tests/test_api_worker.py tests/test_repository.py -q` — **38 passed, 18 skipped**. Skips are PostgreSQL-specific repository/race coverage: no `TEST_DATABASE_URL` was configured and SQLite does not substitute for PostgreSQL row-lock behavior.
- `.venv/bin/ruff check src/supplement_advisor/tasks.py src/supplement_advisor/schemas.py src/supplement_advisor/agents/collection_graph.py tests/test_supplement_review.py tests/test_supplement_backend.py tests/test_supplement_agents.py scripts/verify_supplement_live.py` — 통과.
- `cd frontend && npm run test:e2e` — **15 passed, 13 skipped** across 28 desktop/mobile project cases. The 13 are project-specific cases for the opposite viewport; all 15 applicable cases passed, including supplement submission/provenance on both desktop and mobile and no horizontal overflow.
- `cd frontend && npm run build` — TypeScript and Vite build passed.
- Desktop/mobile screenshots (`frontend/work/verification/supplement-{desktop,mobile}-{form,report}.png`) visually checked. Form copy says adding ingredients replaces the old list; empty amount/unit/basis stay unknown. Layout is legible at both viewport sizes.
- Logs: `work/verification/2026-11-09-supplement-qa-{pytest,ruff,e2e,build}.log`.

## 범위와 남은 검토

Agent의 보완 출처·field_sources·원문 성분 보존/대체·문자열 함량 처리와 보고서 형식은 코드 및 모의 검사를 검토했다. Live verification script의 최신 변경은 manual identity 3개 `user-input` provenance와 수동 성분의 출처/null 보존을 assertion한다. 로컬 호스트 제한과 비밀값 미출력 구조도 확인했다. 이 스크립트는 사용자 승인 범위의 실제 통합 단계에서 root가 실행할 수 있도록 소스 검토만 했고, QA에서는 실행하지 않았다. 실제 PostgreSQL 경쟁 검사 및 live path 증거는 별도 통합 확인으로 남는다.

## 검사 대상 소스 SHA-256

| 파일 | SHA-256 |
|---|---|
| `src/supplement_advisor/tasks.py` | `d069d66ea38d89be3e9869877d6a5bb4d3f539fe6e4787322b100cbbf1c43dd2` |
| `src/supplement_advisor/schemas.py` | `82c53afc3a01d8d3629f869af1e7f5d0ca4eb15bf6b1db9df9456f2cee1f326b` |
| `src/supplement_advisor/main.py` | `236e758d33aade49361de60be9134d9fe0dcea7cea4f27449a02248abd2dc912` |
| `src/supplement_advisor/repository.py` | `abf7422392b1b6a048a80d704efddee1fca12720917ba22f92ace47fdfdd883b` |
| `src/supplement_advisor/models.py` | `d3fa8a8f1449f8d5fb5178d46d8b32e4cdc3bf58a8165bab75a4d819311a7c5d` |
| `src/supplement_advisor/agents/collection_graph.py` | `4400bf31ec5ffb1fa8f8837ec9ae03c721d7adea7533b742bcbc6aa4b0e81cb4` |
| `migrations/versions/0002_m1_supplement.py` | `616455a40328061a3cb56ce531a88b4309765680f13db7843f469cd6aa9bc4b0` |
| `scripts/verify_supplement_live.py` | `5e2ddd67769c05ed3df39fe37b5b9fd855bd9426db60fe4f857a96eeb109fc11` |
| `tests/test_supplement_review.py` | `37be3542ba18cc545c0c5294e62f321c2422c9225398009089a11db403a5a5db` |
| `tests/test_supplement_backend.py` | `ca42b3e5ec28cff8cfa3e7a63ca2ceecc81ca47254c9d59fda4db832296c80e0` |
| `tests/test_supplement_agents.py` | `5bf66f76b345efeffbedbc2845a3538ad56fca93f88ab8e249549292f38b15da` |
| `frontend/src/main.tsx` | `800e3e76e1a3830aa94d844e7fb80f2754fb5679261e85f14829d5a01a01dc5e` |
| `frontend/src/Report.tsx` | `267f58e257f5e978e6ff81c1379628e4c1695b7e51a5f07b4d5be4517716214d` |
| `frontend/src/types.ts` | `67c12f02512c82d964629e9e6cb0f07246aa11197adbf6f83c3bfe7fb012ee2a` |
| `frontend/e2e/analysis.spec.ts` | `6335f7977807becb7a424eb07dbb94300bb19a6d16b9418c893b8c382a65c1b5` |

## 최종 통제 live 증거 대조

Root가 생성한 `work/verification/2026-11-09-supplement-live.json`을 읽어 검증 스크립트의 assertion과 대조했다. artifact의 `status`는 `passed`; 입력은 `controlled_db_seed_and_official_record_derived_manual_input`, `independent_vendor_match=false`로 표시된다. 따라서 이는 독립 판매 페이지 매칭 positive가 아니다.

- 스크립트가 성공 상태를 반환하려면 supplement POST가 202, 틀린 토큰이 404, 중복 POST가 409여야 한다. artifact에는 404/409와 success가 기록돼 있으며, 202 assertion은 script 성공으로 통과한 것으로 확인했다.
- 실제 통합 경로의 결과는 `completed`, `supplemental_input_used=true`, `can_supplement=false`; 공식 대조는 `verified`다. `collection_only`, `score=null`, `verdict=hold`를 유지했다.
- 누적 계수는 attempt `1→2`, reserved seconds `60→120`, tool calls `1→2`; `started_at`은 동일했다.
- 제품명·제조사·신고번호의 `field_sources`는 모두 `user-input`; 수동 성분의 `source_id=user-input`, amount/unit/basis는 모두 null이다. 추가 model/collection call은 `0`으로 기록됐다.
- artifact와 4개 QA log의 민감 필드명/일반 token-key 패턴을 값 출력 없이 검사했다. 민감 필드명 및 secret pattern은 발견되지 않았다.
- 최종 소스 동결 재확인: live script SHA-256 `5e2ddd67769c05ed3df39fe37b5b9fd855bd9426db60fe4f857a96eeb109fc11`; worker `d069d66ea38d89be3e9869877d6a5bb4d3f539fe6e4787322b100cbbf1c43dd2`; supplement Agent `4400bf31ec5ffb1fa8f8837ec9ae03c721d7adea7533b742bcbc6aa4b0e81cb4`; independent review test `37be3542ba18cc545c0c5294e62f321c2422c9225398009089a11db403a5a5db`. Matches the hashes above.
