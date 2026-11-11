# M1 공식 주요 원료 추출 프롬프트 독립 QA

## Prompt 범위 확인

`src/supplement_advisor/agents/collection_graph.py::_extract`의 시스템 지시를 확인했다. 원재료 목록뿐 아니라 영양·기능정보 표에서 성분명·함량·단위·섭취 기준을 각 필드로 추출하라고 명시한다. 원산지는 성분명/섭취 기준에 포함하지 않고 basis에는 섭취 기준만 넣도록 했으며, 상표·기능성 등록 코드를 보존하고 함량·단위 환산과 추정을 금지한다.

수정은 시스템 프롬프트에 한정됐다. `Extraction` 필드 구성은 기존 그대로이며 GPT-5.6 Luna, reasoning none, `max_output_tokens=4000`, 외부 timeout 15초, 호출예산과 grounding 절차를 유지한다. collection snapshot version은 7이다. 버전 6 snapshot 재사용 금지 회귀도 실행했다.

## 이전 ER Hana artifact 대조

읽기 전용 확인 artifact: `work/verification/2026-11-10-registration-match-url.json`, SHA-256 `9bf59f44004062eb6bf5fac1d04806c907e0adc66bff6032f7b50d53cb1bedb3`.

artifact는 `2026-11-10T06:15:20Z` 생성, extraction status `extracted`, official state `candidate`, 판정 `not_demonstrated`다. report는 원재료목록의 혼합제제 등 9개 성분만 ingredients로 반환했고, 독립된 비타민D/비타민K 성분 함량 항목은 반환하지 않았다. `claims`에는 D/K 기능 문구가 있어 페이지의 기능표 관찰이 전혀 없었던 것은 아니지만, 각 D/K 함량·단위·basis는 없었다. 원료 목록의 루바브와 해조칼슘·목화씨앗유 표기에는 원산지가 성분명 괄호 안에 포함됐다. 공식 `RAWMTRL_NM` 주요 원료 세 항목은 모두 evidence `missing`이고, 결과는 candidate로 안전하게 남았다.

이 artifact는 새 프롬프트의 변경 전 기준이다. 이번 QA는 해당 JSON을 읽기만 했고 모델이나 FDA API를 호출하지 않았다. 프롬프트 텍스트/계약 테스트는 통과했지만 새 추출 지시가 실제 페이지에서 D/K 항목을 추출하는지는 다음 승인된 fresh URL 확인 전까지 입증되지 않았다. candidate를 positive나 프롬프트 성공으로 해석하지 않는다.

## 회귀

- `tests/test_registration_name_review.py` 및 기존 `tests/test_agents.py::test_previous_version_failed_snapshot_is_not_reused`: **15 passed**.
- `ruff check tests/test_registration_name_review.py`: 통과.
- `git diff --check`: 통과.
- 독립 prompt 회귀는 표 추출 범위, 원산지/basis 분리, 상표·코드 보존, 변환·추정 금지와 모델/none/4,000/schema 유지에 한정한다. 기존 주요원료 전체 일치, 부원료 대체 금지, number/maker conflict, 중복/절단 후보, 함량 기준 모순 회귀도 함께 통과했다.

실모델·공식 API 호출은 포함하지 않았다. 실제 추출 개선 여부는 이후 fresh URL artifact를 기존 URL/API 입력에 역주입하지 않고 확인해야 한다.

## 오프라인 grounding 원인 가설 확인

새 fresh URL artifact `work/verification/2026-11-10-registration-match-final-url.json` (분석 ID `fe90bad8-94c9-4e2f-9500-1bb2ee350b4a`, SHA-256 `0270cbdfc0e5efddae4c6cbfb7438fcd0d420e1ca96439caf6aed67dd21d595b`)도 candidate다. 이 report의 ingredients에는 주요 원료 중 루바브가 match로 있고 비타민 D/K는 missing이다. D/K 영양 항목과 관련 claim도 JSON에 없다. artifact는 원본 모델의 parsed payload/excerpt 전체를 저장하지 않으므로 실제 누락 원인은 이 파일만으로 특정할 수 없다.

오프라인에서 동일 이름·숫자·기준을 갖춘 synthetic `Extraction`을 `_ground_extraction`에 넣어 단위 기호 가설을 분리 확인했다. 문서 원문 `비타민D 10㎍/0.08g`에 모델 excerpt `비타민D 10 μg/0.08g`, unit `μg`를 넣으면 원문 정규화는 공백만 제거하므로 excerpt 전체가 원문에 없다고 판단되어 성분행이 통째로 제외된다. excerpt와 unit이 원문 기호 `㎍`를 보존하면 같은 구조의 행은 통과한다. 이는 제안된 glyph mismatch가 grounding에서 행 누락을 재현할 수 있음을 보여준다.

이 재현은 실 parsed excerpt가 `μg`였다는 증거가 아니다. 등록코드·원료 이름 표기 또는 다른 excerpt 형식도 현재 JSON으로는 확인할 수 없다. 모델/API 추가 호출이나 코드 변경 없이 오프라인 synthetic과 기존 artifact만 사용했다. 다음 root raw-parsed 관찰로 실제 원인을 확인하기 전까지 이 설명은 검증된 원인으로 단정하지 않는다.
