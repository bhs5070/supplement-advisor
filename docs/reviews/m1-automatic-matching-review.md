# M1 자동 공식 후보 대조 독립 QA

작성자와 분리한 검토. 범위는 `src/supplement_advisor/agents/collection_graph.py`, `frontend/src/**`, 자동 매칭 브라우저 계약 및 cached/URL 검증 하네스다. 구현 코드는 수정하지 않았고 독립 회귀만 `tests/test_automatic_matching_review.py`에 추가했다.

## 필수 지적 및 수정 확인

| 항목 | 재현 조건과 영향 | 최소 수정 | 상태 |
|---|---|---|---|
| 제품명 구두점 제거 | `홍삼(농축)`과 `홍삼농축`, `A-B`와 `AB`가 같은 이름으로 정규화되면 변형 제품을 동일 제품으로 확정할 수 있었다. | 제품명은 공백만 동등 처리하고 괄호·구두점은 유지한다. 제조사 법인기호 정규화는 별도 적용한다. | 수정 확인: `_product_identity_normalized`; 독립 회귀 통과 |
| 성분 괄호 전체 삭제 | `(발효)` 등 성분 형태를 나타내는 괄호가 사라지면 서로 다른 원료가 보조근거로 세어질 수 있었다. | 명시적인 원산지·수량 괄호만 정리하고 변형 설명은 보존한다. 부분문자열 원료 일치도 금지한다. | 수정 확인: `_ingredient_name_key`; 독립 회귀 통과 |
| 공통 기본원료 2개 오인 | 정제수·홍삼만으로 특징성 성분 근거 2개를 충족할 수 있었다. | 비특징 원료 집합을 제외하고 정확히 다른 특징성 보조원료 2개를 요구한다. | 수정 확인; 독립 회귀 통과 |
| 함량 단위 경계 및 다른 성분 값 차용 | 아연 `10 g`과 공식 `아연 10 mg`에서 `g`가 `mg` 부분문자열로 일치하거나, 수량만 있고 단위 없는 표시가 함량 근거로 취급될 수 있었다. | 이름이 정확히 일치하는 단일 성분 항목 안에서 숫자·단위를 경계 검사하고, 두 값이 있을 때만 동일 함량 근거로 인정한다. 숫자/단위 없는 비교는 `missing`으로 둔다. | 수정 확인: `_contains_unit`, `_additional_evidence_rows`; 독립 회귀 통과 |
| 검색집합 완전성 메타데이터 | `total_count`가 반환 수와 모순되거나 bool/잘못된 형식이면 일부 후보만 보고 유일성을 과장할 수 있었다. | 음이 아닌 정수 또는 숫자 문자열만 허용하고 `total_count != returned_count`를 불완전으로 표시한다. | 수정 확인; 작성자 회귀 통과 |
| 신고번호 중복 충돌 | 동일 신고번호지만 필드가 다른 공식 응답 row를 하나로 덮어쓰면 충돌이 숨겨질 수 있었다. | row 전체 내용 hash로 별도 보존하고, 같은 번호의 다중 row가 있으면 번호 우선 판정도 matched를 금지한다. | 수정 확인; 구현 검토 및 작성자 회귀 통과 |
| 번호 없는 확인 설명 | 번호가 없는 제품도 공통 `registration_matched` 문구에서 페이지 신고번호가 일치했다고 표시할 수 있었다. | 번호가 있을 때와 없을 때 설명을 나누고, 번호 없는 경우 원문 제품명·제조사와 보조근거 조건을 명시한다. | 수정 확인; 독립 회귀 통과 |
| 보완 후 이전 공식 출처 잔류 | 과거 해시형 I0030 후보 source가 supplement 결과의 새 판정과 함께 남을 수 있었다. | `kind=official` 및 I0030 source ID prefix로 과거 후보/판정 출처를 제거 후 새 결과만 추가한다. | 수정 확인; 코드 검토 |
| 성분만 보완한 provenance 누락 | 제품 identity는 판매 페이지에서 오고 보조 성분만 사용자 입력이면 해당 evidence가 `user-input` 출처를 링크하지 않을 수 있었다. | identity와 ingredient 출처 목록을 따로 전달하고 보조 성분 evidence의 source_ids에 실제 성분 출처를 넣는다. | 수정 확인; 코드 검토 |
| Matched 화면 fixture 내부 모순 | frontend matched 시나리오는 제품 페이지 신고번호가 `null`인데 공식 번호 evidence를 missing으로 남겨둔 채 reason을 페이지 신고번호·제품명·제조사 일치로 바꿨다. 제품번호를 실제 제품 필드에 덮어쓰지는 않지만 fixture가 계약과 다른 positive 사례를 표현했다. | numberless success fixture는 신고번호가 원문에 없음을 유지하고, 이름·제조사+정확한 추가 함량근거가 complete unique 후보와 일치한다고 reason/evidence/check를 정합시킨다. | 수정 확인: numberless 근거만 표시, 번호 필드 null 유지; desktop/mobile Chromium 재검증 통과 |

## 근거 및 범위

- 계약은 번호 없는 `matched`에 이름·제조사 동등성, 완전한 검색집합, 정확한 추가 근거, 모순 없음 및 단일 후보를 요구한다. API record 값을 모델 입력에 역주입하지 않으며 제품 원문 신고번호를 공식 번호로 덮어쓰지 않는다.
- Cached 공식 응답 `work/verification/2026-11-09-official-candidate-evidence-fields.json`은 `에브리타임샷`과 `에브리타임샷스트롱`을 별도 record로 반환하고 `total_count=2`, 반환 2건이다. 페이지 원문 저장본 `work/verification/2026-11-09-domestic-matching-live.json`은 판매 페이지 원문·독립 추출에서 신고번호가 없었던 기존 표본이다. 이것은 캐시 원문 관찰이며 이번 QA에서 실 API를 호출하지 않았다.
- 리드가 작성자 동결본으로 수행한 cached independent extraction + live I0030 결과는 `work/verification/2026-11-09-automatic-matching-cached.json`에 기록됐다. 성공 레코드 2건 중 `matched=0`, `candidate=1`, `unverified=1`, 실패/보고서 누락 1건이며 상태는 `not_demonstrated`. 두 query 표현에서 동일 이름·제조사의 복수 후보가 관찰되어 보수적으로 candidate를 유지했다. 이것은 작은 cached 표본의 재대조이지 새 모델/판매 페이지 실행은 아니다.
- `scripts/verify_automatic_matching_live.py`는 기본 cached 모드에서 기존 독립 페이지 추출을 재사용하고 새 모델/페이지 호출을 하지 않으며, FDA API 호출은 별도로 발생하므로 이번 QA 실행에서는 호출하지 않았다. `--live-url` 경로는 loopback stack을 제한하고 예상 신고번호를 assertion으로만 사용하며 인증 토큰을 출력·저장하지 않는다. 하네스의 실제 실행·실 URL 성공은 이 QA 판정에 포함하지 않았다.

## 검증

- `./.venv/bin/python -m pytest tests/test_agents.py tests/test_supplement_agents.py tests/test_automatic_matching_review.py -q --tb=short`: **43 passed**. 실행본은 모의 API/모델 테스트이며 live API 성능 증거가 아니다.
- `git diff --check`: 통과.
- Frontend Chromium 전용 5174: 이전 전체 **17 passed, 13 skipped**. fixture 수정 후 `npx playwright test --grep "separates an official candidate"`: **2 passed** (desktop/mobile); 캡처 갱신과 `npm run build` 통과.
- **판정 제한:** 브라우저 검증은 fixture/mock 계약이다. 독립 QA는 실 모델/FDA 호출을 하지 않았다. 리드 cached live-I0030 재대조에서 자동 matched는 0건이므로 URL 자동 매칭 목표는 입증되지 않았고, 작은 표본은 일반 성능을 나타내지 않는다.
