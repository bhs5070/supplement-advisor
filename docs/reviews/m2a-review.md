# M2-A 최종 독립 검토와 제한 마감

검토자: 새 독립 Luna `m2a_final_review`. 제품/테스트 작성자가 아니며 전체 baseline→candidate diff와 승인 설계·계획을 읽기 전용으로 검토했다. 보고된 테스트를 반복하지 않았다.

## 최초 판정

Task5 Spec ❌ / Quality Needsfixes / 로컬 실연동 준비 No.

필수 문제는 두 가지다.

1. 일반 원료 자료가 official이라는 이유로 product_applicable을 통과할 수 있다. NIH ODS 같은 일반 설명을 완제품 효과로 확대하지 않도록 적용성을 제한해야 한다.
2. M2의 초기 페이지 요청에는 요청 전 durable in-flight 표식이 없다. 결과 저장 전 중단되면 재수집할 수 있으므로, 표식 저장 후 요청하고 복원 시 불명확한 요청을 자동 반복하지 않아야 한다.

검토 당시 필수 문서 미마감도 지적했다. 이 파일과 작업판·인계·검증 기록은 리드가 현재 결과에 맞춰 정리한다. 당시 Task5 진행 중 표시는 미배포·미연동 상태를 반영한 것이며 완료 주장으로 사용하지 않는다.

## 사용자 선택에 따른 범위

사용자가 weekly limit 임박을 알렸고 **A: 필수 두 건 수정·관련 테스트·독립 재검토·인계 기록**을 선택했다. 로컬 실행 반영과 실제 URL 검증은 다음 한도로 이관한다. 최종 수정과 scoped 재검토 결과는 아래에 추가한다.

## 보류한 Minor

verifier 카운터의 음수/bool 거부 및 실제 --output artifact 비밀값 제거 회귀 검사를 강화할 수 있다. 현재 제품에서 해당 음수/불린 카운터가 만들어지는 증거와 직접 유출 증거는 확인하지 못했다. 이번 한정 수정에서는 보류한다.

## 검증 범위

최종 수정 전 candidate: 실제 PostgreSQL UUID 격리 schema 포함 전체342 passed/4 skipped, 실제 Chromium API fixture26 passed/22 project-filter skips, Ruff 통과. UI build는 같은 UI hash의 Task4fix2 통과 증거다. 모델/검색 provider는 모의이며 실제 외부 연동은0건이다. 배포·실행본 hash·실제 URL 확인을 이 결과로 대신하지 않는다.

## A 선택 최종 마감 결과

두 필수 지적은 모두 **ADDRESSED**다. 일반 원료 자료를 완제품 적용으로 승격하지 않고 M2 미평가로 제한한다. 초기 M2 HTTP 요청은 각 hop 전에 fenced 표식을 저장하며, M1 보고서와 원문 경로의 저장이 끝날 때 함께 해제한다. 불명확한 표식 복원은 재요청 없이 unknown_interrupted 부분 보고서로 종료한다.

scoped 재검토에서 발견한 새 usage.total=0 회귀도 정정했다. 같은 worker의 오류 및 재시작 복원 모두 DB를 새로 읽어 누적 예약을 보존한다. 역할별 귀속은 null/unavailable다. 최종 검토자는 **카운터 회귀 ADDRESSED / scoped quality Approved / 새 회귀 없음**으로 보고했다.

검증: 필수 두 동작 RED2→지정90 passed/5 PostgreSQL 조건 skips/Ruff, 이후 카운터 정정 RED1→대상1 passed/Ruff. 검토자는 테스트를 반복하지 않았다. 이 제한 마감은 Task5 전체 완료나 실연동 준비 완료 판정과 구분한다. 최종 수정본의 실PG 전체 회귀·서비스 반영·실URL은 다음 한도에 수행한다. 최신 hash와 범위는 `work/verification/m2a/checkpoint-source-sha256.json`, `closure-verification.json`에 있다.
