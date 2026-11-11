# M2-A 구현계획 한정 EGM persona 검토

대상: [구현계획](../superpowers/plans/2026-11-11-m2a-evidence-review.md), [설계](../superpowers/specs/2026-11-11-m2a-evidence-review-design.md). 사용자 설계 승인과 계획/검토/TDD 계속 지시 후 수행했다.

## 실행 범위

설치 EGM의 implementation_readiness, codebase_details, style persona와 implementation-readiness-standard를 실제 읽은 새 컨텍스트 Luna 검토자3개를 직접 호출했다. 각 보고에서 실제 읽은 목록과 검토 완료 여부를 확인했다. 수정·외부 호출·테스트·하위 Agent는 허용하지 않았다. 대화 이력을 전달하지 않았으나 AGENTS/파일시스템까지 격리됐다고 주장하지 않는다.

이번 실행은 설치된 persona/표준을 사용한 한정 구현준비 점검이다. egm-review의 전체5단계·상호작용checkpoint·egm-review-loop의표준수렴 절차를 수행하지 않았고 그 완료·수렴을 주장하지 않는다. 사용자가 승인한 설계 내 구현 명확화만 반영한다. 설계 방향 변경은 별도 사용자 결정 대상이다.

## 초기 발견과 처리

| 검토 | 중요도 | 발견 | 처리 |
|---|---|---|---|
| readiness | Major | 도구reserve와DB예약/role계수연결미정 | 단일callback/owner고정/DB(0,1)/저장후요청/재시도별차감명시 |
| readiness | Major | snapshot schema·복원판정미정 | version/phase/fingerprint/counters/in_flight/결과와source필드명시 |
| readiness | Major | frontend테스트경로조건부 | 실제Playwright testDir확인후frontend/e2e/research.spec.ts고정 |
| readiness | Nit | 문서경로약어 | docs/아래정확경로명시 |
| codebase | Major | 마지막attempt queued yield시claim의max_attempt실패와충돌 | 3번째시도안에서먼저terminalpartial확정 |
| style | Major | 설계초안상태와사용자승인주장모순 | 상세설계제시후가자승인시점기록,계획개별명세는리드제안으로구분 |
| style | Major | REQUIRED와recommended혼용 | 사용자팀실행선호에따라subagent-driven한경로고정 |
| style | Nit | 한국어/기술용어공백부족 | 핵심순서·상태명확화,문체개선은기능게이트로과대평가하지않음 |

첫수정재검토에서마지막시도/경로/승인표현은해결됐고,owner/DB차이/예약-저장순서와손상snapshot예외가남았다. 리드가명시순서와snapshot_invalid/incompatible무호출종료를추가했다. 다음새컨텍스트경계검사에서DB예약후snapshot저장전crash의owner예약차이를지적했다. 원인을재검토해맥스보정/추정배분방식을버리고불변collection_tool_calls와정확한DB==snapshot==baseline+owner합검증으로전략을바꿨다. 불일치와research시작후snapshot부재는budget_state_mismatch/partial/외부요청0이다.

그한지적을독립검토자에게재확인했고 **“이전 Major는 해결됐습니다…요청한 범위에서 남은 필수사항은 없습니다.”**라는결과를받았다. 이판정은문서의해당경계명세에대한것이며실제구현의예산/복구검증은Task2/3및독립QA에서별도로수행해야한다. 저중요도문체때문에전체검토를반복하지않는다.
