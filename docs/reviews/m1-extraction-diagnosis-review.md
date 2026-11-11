# M1 추출 실패 최소 진단 독립 QA

작성자와 분리한 검토다. 범위는 `src/supplement_advisor/agents/collection_graph.py`, live 검증 하네스의 진단 출력, 그리고 독립 회귀 `tests/test_extraction_diagnosis_review.py`다. 추출·매칭 구현 코드는 수정하지 않았다. 회귀 실행 중 확인한 기존 보완 출처 테스트의 정확한 ID 기대값 두 건만 계약 의미에 맞게 고쳤다.

## 검토 결과

| 항목 | 검토 및 결과 |
|---|---|
| 진단 코드 allowlist | 추출 상태는 `extracted`, `not_configured`, `budget_exhausted`, `timeout`, `authentication_failed`, `permission_denied`, `rate_limited`, `connection_failed`, `provider_error`, `invalid_response`, `incomplete`, `refused`, `request_failed`만 보고서에 내보낸다. 유효하지 않은 내부 코드는 `extraction_status`에 복사되지 않는다. 통과 |
| SDK 예외 분류 | SDK timeout, 인증, 권한, rate limit, 연결, provider status, 파싱/검증 오류와 incomplete/refusal 유형을 분리한다. 400 및 별도 하위유형이 없는 API status 오류는 `invalid_response` 또는 5xx `provider_error`로 분류한다. 알 수 없는 예외는 `request_failed`다. 예외 메시지 내용에 의존하지 않는다. 통과 |
| 응답 상태 | 명시적인 `incomplete`와 refusal content만 각각 해당 코드로 분류한다. parsed 결과가 없지만 refusal 근거도 없는 응답은 `invalid_response`이며 추출 성공으로 바뀌지 않는다. 통과 |
| 비밀정보 경계 | 보고서에는 code만 저장하며 예외 텍스트, URL, header, body, 키나 token을 보고서에 넣는 경로가 없다. 진단 코드에는 예외 문구/provider detail을 연결하지 않는다. 모의 rate-limit 오류에 민감 문자열을 넣은 보고서 회귀가 통과했다. 이 호출 경로는 예외를 삼키고 별도 로그를 남기지 않는다. |
| 실패 시 제품 판정 | 추출 실패 check는 `unavailable`이고 확인 가능한 추출값을 만들지 않는다. 보고서 점수는 `null`, 판정은 `hold`로 유지된다. 공식 매칭 계약의 실패 판정을 바꾸지 않는다. 통과 |
| 실행 한도·재시도 | `external_timeout_seconds` 예약, 최대 호출 수, SDK `max_retries=0` 및 기존 snapshot/fencing 흐름을 유지한다. 모델·상한·공식 대조 조건 변경을 확인하지 않았다. collection snapshot version은 3으로 올라 과거 진단 없는 추출 snapshot을 새 상태로 오인하지 않는다. 통과 |
| live 검증 하네스 | URL 통제 검사에서 `extraction_status.code == "extracted"`를 요구하고 결과에 제한된 code 객체만 포함한다. 이 QA에서는 하네스를 실행하지 않았다. 실 URL·실 모델·FDA 호출 증거로 세지 않는다. |

필수 수정 지적은 없다. 실패 코드가 UI의 기존 `표시 정보 추출` check를 `unavailable`로 유지하고 한국어 사유만 노출하는 점도 확인했다. 이전 보고서는 optional field를 읽지 않아도 되며 API 저장·조회 경로는 report dict를 보존한다.

## 추가 회귀와 기존 테스트 기대값

독립 파일은 SDK typed exception의 allowlist 매핑, builtin timeout과 unknown fallback, 구조화 refusal/incomplete/설명 없는 빈 응답 분류, 민감한 rate-limit 응답의 보고서 비노출을 검사한다.

최초 관련 회귀 실행은 **61 passed, 2 failed**였다. 두 실패는 supplement report가 공식 후보의 hash source ID를 check에 추가한 현재 계약과 기존의 고정 source ID 목록 기대가 달라서였다. 결과를 줄여 맞추지 않고 `tests/test_supplement_review.py`의 두 기대를 의미 검증으로 바꿨다. 성분만 보완한 경우 page identity source를 포함하고 `user-input` identity source를 추가하지 않는지, 신고번호를 보완한 경우 page와 user input을 모두 포함하는지 확인한다. 두 경우 모두 check가 가리키는 모든 source ID가 report의 `sources`에 존재하고 공식 후보 ID가 포함되는지도 확인한다. 이는 새 extraction 진단 결함이 아니라 stale한 exact-ID assertion이었다.

## 검증

- `./.venv/bin/python -m pytest tests/test_extraction_diagnosis_review.py tests/test_agents.py tests/test_supplement_review.py -q --tb=short`: **63 passed**.
- `./.venv/bin/ruff check src/supplement_advisor/agents/collection_graph.py tests/test_extraction_diagnosis_review.py tests/test_agents.py tests/test_supplement_review.py scripts/verify_automatic_matching_live.py`: 통과.
- `git diff --check`: 통과.
- 실 모델·외부 API·FDA 호출: 수행하지 않음.

## 판정 한계

분류 동작은 SDK mock과 코드 검토로 확인했다. 마지막 URL 실패의 실제 원인은 미분류 상태로 남는다. 이번 결과는 이전 15.1초 실패가 timeout이었다는 증거가 아니며, 추출 성공률이나 매칭 품질도 입증하지 않는다.

## 확인된 timeout 후 최소 reasoning 변경 QA — 2026-11-10

리드의 실 URL 진단 기록 `work/verification/2026-11-10-extraction-diagnosis-url.json`에서 typed `timeout`을 확인했다. 이는 앞선 15.1초 경과를 근거로 한 추정과 구분되는 신규 진단 결과다. 작성자 변경은 Responses API parse에 `reasoning={"effort":"low"}`를 전달하고 collection snapshot version을 3에서 4로 올린 것이다. supplement snapshot은 version 3으로 유지했다. 모델, 요청 원문·schema, output 4,000, 외부 15초, 시도 60초, 활성 180초, 예산, grounding 및 공식 매칭 조건은 바뀌지 않았다.

독립 회귀 `test_low_reasoning_retries_old_timeout_snapshot_as_safe_timeout`은 이전 version 3 timeout snapshot이 재사용되지 않아 새 모델 요청이 한 번 실행되고, reasoning low·기존 모델/output/schema/input이 전달되며, typed timeout이 안전하게 `timeout` 보고서로 남는 것을 확인한다. 실패 check는 unavailable, 점수는 null, 판정은 hold다. 기존 `test_numberless_name_hit_is_candidate_if_query_total_missing_or_ingredient_conflicts`도 회귀 묶음에서 통과해 불완전 검색집합과 근거 불충분 후보가 candidate로 남는 것을 확인했다.

검증:

- `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/private/tmp ./.venv/bin/python -m pytest -p no:cacheprovider -s tests/test_extraction_diagnosis_review.py tests/test_agents.py tests/test_automatic_matching_review.py tests/test_supplement_review.py -q --tb=short`: **73 passed**. `-s`는 테스트 캡처 tempfile을 만들지 않도록 사용했다.
- `./.venv/bin/ruff check src/supplement_advisor/agents/collection_graph.py tests/test_extraction_diagnosis_review.py tests/test_agents.py`: 통과.
- `git diff --check`: 통과.
- 이번 독립 QA에서는 실 모델·실 URL·FDA 호출을 수행하지 않았다. root가 기록한 신규 URL 결과만 근거로 참조한다.

`low`가 실제 완료시간이나 품질을 개선하는지는 아직 확인되지 않았다. 이는 낮은 reasoning effort가 속도와 토큰 사용을 줄일 수 있다는 공식 안내에 근거한 제한된 설정 가설이며, 신규 URL 성공·후보 모호성 해소 또는 일반 품질 향상을 보장하지 않는다.

## 마지막 제한 실험: reasoning none 독립 QA — 2026-11-10

리드의 live 기록은 이전 KGC 1건에서 추출 완료 후 공식 대조가 `candidate`였고, 별도 ER Hana low 시도 1건은 추출 `timeout` 및 공식 조회 0건이었다. 따라서 low 변경이 모든 URL에서 timeout을 해소했다는 주장은 할 수 없다. 계약에 따라 마지막 제한 수정은 같은 모델의 공식 지원 reasoning `none`과 collection snapshot version 5로 한정했다. 이전 v4 timeout snapshot을 재사용하지 않게 한다.

독립 회귀 `test_none_reasoning_retries_previous_timeout_snapshot_as_safe_timeout`은 이전 v4 timeout snapshot에서 새 parse 요청을 수행하고 `reasoning={"effort":"none"}`을 전달하며 모델, 입력 원문, 구조화 schema, output 4,000, SDK 재시도 0을 보존하는지 검사한다. 모의 typed timeout은 여전히 allowlist 코드 `timeout`으로 보고되고 표시 추출 check는 unavailable, 점수는 null, 판정은 hold다. `test_numberless_name_hit_is_candidate_if_query_total_missing_or_ingredient_conflicts` 및 매칭 회귀 전체도 함께 실행해 후보 모호성/불완전 집합 보수 판정이 유지됨을 확인했다. 수정은 QA 소유 테스트와 이 리뷰 기록에 한정했다.

검증:

- `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/private/tmp ./.venv/bin/python -m pytest -p no:cacheprovider -s tests/test_extraction_diagnosis_review.py tests/test_agents.py tests/test_automatic_matching_review.py tests/test_supplement_review.py -q --tb=short`: **73 passed**.
- `./.venv/bin/ruff check --no-cache src/supplement_advisor/agents/collection_graph.py tests/test_extraction_diagnosis_review.py tests/test_agents.py`: 통과.
- `git diff --check`: 통과.
- 독립 QA는 실 모델/API를 호출하지 않았다. ER Hana 후속 실제 URL은 아래에서 별도로 읽기 전용 확인했으며 mock 검사 결과와 합산하지 않는다.

Reasoning `none`의 추출 완료시간이나 정확도 효과는 미확정이다. 이는 제한된 마지막 실험 설정일 뿐 성공 보장이 아니다.

## 최종 실증거 읽기 전용 대조 — 2026-11-10

`work/verification/2026-11-10-low-kgc-url.json`과 `work/verification/2026-11-10-none-independent-seller-url.json`을 읽기 전용으로 확인했다. 새 호출·테스트·코드 변경은 하지 않았다.

| 분석 | 원문 추출 identity | 공식 검색 분모·응답 | 판정 |
|---|---|---|---|
| Low KGC | 제품명 `에브리타임 샷`, 제조사 `㈜한국인삼공사`, 신고번호 없음 | 제품명 두 query에서 각각 3/3, 2/2 반환. 결과 보고서에는 5개 공식 후보 record/source가 보존됨. 이름 변형 `에브리타임 샷`, `에브리타임샷`, `에브리타임 샷 골든 포뮬러`, `에브리타임 샷 코어`, `에브리타임샷스트롱`과 제조사 표기를 확인 | `official_match=candidate`, `matched_record=null`, 분석 `needs_input`; 독립 자동 positive 0 |
| None ER Hana | 제품명 `ERr731® 여성 갱년기영양제`, 제조사 `(주)서흥`, 신고번호 `200400200062002` | 신고번호 query 1/1 반환. 공식 record는 `이알하나 ERr731`, 제조사 `(주)서흥`, 같은 신고번호. 공식 source의 document ID와 update version은 report에 보존됨 | 제품명 문자열이 엄격한 현행 일치 조건을 충족하지 않아 `candidate`, `matched_record=null`, 공식 check `unverified`. 분석 자체는 `completed`지만 검증 하네스는 positive 조건 미달로 `not_demonstrated`; 독립 자동 positive 0 |

두 artifact 모두 페이지와 공식 후보를 별도 source로 남겼다. KGC official check는 이름·제조사 후보가 여럿인 상황에서 확인으로 올리지 않았다. ER Hana는 제조사와 신고번호가 일치해도 페이지명 `ERr731® 여성 갱년기영양제`와 공식명 `이알하나 ERr731`의 문자열 차이를 자동 동의어 처리하지 않았다. 이는 현행 계약을 따르는 보수적 결과이며 페이지 원문이 공식 이름과 다른 실제 alias 관계인지, 추가 identity 규칙이 필요한지는 자동 확인된 사실로 취급하지 않는다.

검증 하네스의 `not_demonstrated`는 실제 분석이 terminal success가 아니었다는 뜻이 아니다. None ER Hana 분석 결과는 `completed`였고, 자동 identity positive의 독립 assertion이 충족되지 않았다는 뜻이다. ER Hana의 공식 검색 분모는 1 query·1 record이며 KGC의 분모는 두 query 각각 3/3과 2/2다. 이 두 편의표본을 기존 국내 표본과 합산하거나 일반 성능률로 해석하지 않는다. 사용자 선택이 대기 중이므로 이 QA는 기존 `candidate` 판정을 유지한 결과만 기록한다.
