# M1 번호 기반 등록 대조와 판매명 차이 독립 QA

작성자와 분리해 backend 계약의 필수 음성 조건과 cached 실증거를 검토했다. 독립 회귀는 `tests/test_registration_name_review.py`에 추가했다. backend/frontend 구현은 이 QA 과정에서 수정하지 않았다.

## 필수 지적

| 항목 | 재현과 영향 | 최소 수정 | 상태 |
|---|---|---|---|
| 같은 주요 원료의 뒤쪽 함량 충돌 누락 | 같은 주요 성분이 페이지 추출에 여러 번 나오고 첫 항목은 함량 없음, 뒤 항목은 `20㎍/1정`인데 공식 표시가 `10㎍/1정`이면 첫 항목만 검사해 충돌을 숨기고 매칭할 수 있었다. | 정확히 일치하는 모든 grounded 항목에서 비교 가능한 값/기준을 검사하고 하나라도 충돌이면 후보로 둔다. | **수정 확인:** `test_registration_gate_does_not_hide_conflict_in_later_same_name_ingredient` 통과 |
| 서로 다른 함량 단위의 임의 충돌 | 페이지 `0.01 mg/1정`, 공식 `10㎍/1정`처럼 단위가 다르면 환산 계약이 없으므로 conflict가 아니라 missing이어야 했다. | 단위가 다르면 변환하지 않고 missing 처리한다. | **수정 확인:** 단위 불일치 회귀 통과 |
| 표준 필드의 기준 뒤 퍼센트 범위 | 공식 표준 `비타민D : 표시량(10㎍/1정)의 80%~180%`에서 기준을 추출하지 못해, 페이지 `20㎍/1정`의 비교 가능한 충돌이 missing 처리됐다. | 표시량 괄호 안의 함량·섭취 기준을 추출해 동일 기준이면 충돌을 남긴다. | **수정 확인:** `test_registered_percent_range_keeps_the_basis_inside_the_declared_amount` 통과 |

부원료만 있는 경우 주요원료 근거는 미충족으로 candidate, 번호/제조사 불일치·중복 row·잘린 집합은 matched가 되지 않는 회귀가 통과했다. 공식 major `RAWMTRL_NM` 전 항목을 매칭하고 일반 `ETC_RAWMTRL_NM`을 대체 근거로 사용하지 않는 것도 확인했다.

## Cached ER Hana 증거 검토

- 입력 `work/verification/2026-11-10-none-independent-seller-url.json`의 SHA-256: `9089fb4d7d3701bd3b66696345d4641a827f87a5bb1a55d692eef1bdaba7630c`.
- cached 대조 `work/verification/2026-11-10-name-difference-cached.json` SHA-256: `f517e67d1e867e32531acd52c5ccc228ae0a99bd50972aedf059f4bfaa218355`. 이 결과는 저장된 페이지 추출을 그대로 사용해 I0030만 1회 호출했고 새 모델 호출 0회다. 페이지 판매명·제조사·신고번호와 공식 record 및 출처를 별도 필드로 보존한다.
- 독립 추출에는 RAWMTRL_NM의 비타민 D·루바브뿌리추출물(ERr731Ⓡ)(제2024-17호)·비타민 K와 이름이 맞는 별도 `비타민D`, `비타민K`, 루바브 표시가 포함된다. `®`/`Ⓡ` 표기만 같은 루바브 이름 비교는 승인 계약 범위다. 혼합제제명을 D/K 원료와 동일시할 필요는 없다.
- 페이지 D/K 함량은 기준이 null이므로 비교 결과 missing이어야 한다. 공식 0.08g 기준과 임의로 비교하거나 변환하면 안 된다. 제형은 현재 페이지 추출 스키마에 없어 missing이어야 한다. 따라서 이 실제 사례의 missing은 모순을 입증하지 않으며, 테스트의 1정 수치 충돌은 별도 음성 합성 회귀다.
- artifact상 seller source와 I0030 official source는 서로 다른 id로 연결되어 있고 신고번호는 원문 product 필드에 보존된다. 이 cached 사례는 실판매 페이지→모델 추출의 기존 결과를 재사용한 1건이며, 일반 매칭 성능 증거가 아니다.

## 회귀 실행

`./.venv/bin/python -m pytest tests/test_registration_name_review.py -q --tb=short`: **13 passed**. `./.venv/bin/ruff check tests/test_registration_name_review.py`와 `git diff --check`도 통과했다. 초기 3개 필수 실패를 구현 수정 뒤 재실행해 통과시켰다. 실 FDA 호출은 수행하지 않았다.

## Frontend 독립 QA

첫 Chromium desktop/mobile 실행에서 comparison-limits 안내가 backend evidence `ingredient_amount`/`dosage_form` key를 인식하지 못해 2개 viewport가 실패했다. 리드가 비교 안내의 두 legacy/current key를 허용하도록 최소 통합 수정한 뒤 같은 독립 QA를 재실행했다. 현재 결과는 **desktop/mobile 2 passed**이며 안내 문구와 한국어 누락 라벨을 확인했다. `npm run build`도 통과했다. 캡처는 [Desktop](../../frontend/work/verification/official-name-difference-desktop.png) 및 [Mobile](../../frontend/work/verification/official-name-difference-mobile.png)이다. 화면에서 판매명 차이, 함량 기준과 제형의 missing 근거, 공식 source record 및 출처가 보인다. 모바일 표는 가로 스크롤 영역 안에 유지되며 전체 페이지 폭은 viewport를 넘지 않았다.
