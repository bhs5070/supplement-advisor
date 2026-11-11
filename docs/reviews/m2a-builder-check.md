# M2-A Superpowers builder check

2026-11-11. 대상은 [M2-A 설계 초안](../superpowers/specs/2026-11-11-m2a-evidence-review-design.md)이다. 독립 Luna를 `fork_turns: none`으로 실제 호출했다. 원문 설계와 필요한 기존 Worker/Repository/Graph/Schema 읽기만 허용했고 파일 수정·실서비스 호출·추가 Agent 생성은 허용하지 않았다. 작성자는 리드이며 검토자와 다르다.

## 첫 검토와 명확화

| 질문 | 구현에 미치는 영향 | 리드의 명확화 |
|---|---|---|
| 보완 후 충분성 기준 | 조사 진입/공식 대조 게이트 | 기존 missing_fields==[]를 사용. 별도의 official matched 강제는 추가하지 않으며 미확인을 확정으로 바꾸지 않음 |
| 보완 후에도 부족한 작업의 상태 | 기존 클라이언트·보완 버튼·오류 의미 | needs_input/insufficient_information 유지, can_supplement=false, 조사 객체에 not_started와 이유 |
| 재조사의 작업 수명주기 | 예산·권한·중복 호출 | Supervisor는 동일 Analysis/남은 예산. terminal 재개 API 없음. 명시적 URL 재접수만 새 Analysis이며 UI 자동 재접수 금지 |

리드가 초안에 반영한 뒤 같은 독립 검토자를 `followup_task`로 실제 재호출해 세 질문만 재확인했다. 최종 답변: **“중요한 미해결 사항 없음. 앞서 제기한 세 질문은 모두 해소됐습니다.”**

이는 Superpowers의 구현 계획 작성 가능성 점검이다. EGM 전체 검토, 임상적 타당성, 구현 동작·실모델/외부 API 성능 검증은 수행하지 않았다. 사용자 설계 승인도 아직 아니다.
