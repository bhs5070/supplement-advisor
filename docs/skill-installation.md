# Codex Skill 설치 결과

2026-11-11. 사용자 승인 후 설치·정책 통합을 수행했다. 작업공간은 `/Users/hyeonseokbae/Desktop/ad_fact_check`다. M2는 보류이며 제품 기능 구현이나 신규 에이전트 생성은 하지 않았다.

## INSTALLED

| 항목 | 버전 | 범위·방식 | 실제 인식 |
|---|---|---|---|
| Superpowers | 7.0.1 | 사용자 전역, 공식 Codex 마켓플레이스 | plugin/installed 활성, plugin/read Skill15개, using-superpowers 본문 조회 성공 |
| EGM | 0.1.1 | 사용자 전역, 공식 google/elephant-goldfish-model marketplace | plugin/installed 활성, plugin/read Skill7개 |
| Archify | 3.2.0 | 프로젝트 `.agents/skills/archify`, 공식 well-known 배포본 복사 | skills/list repo scope, enabled |
| UI UX Pro Max | CLI 2.15.0 | 프로젝트 `.agents/skills/ui-ux-pro-max`, 공식 배포 CLI 템플릿 | skills/list repo scope, enabled |
| UI 보조 Skill6개 | 위 CLI 번들 | banner-design, brand, design, design-system, slides, ui-styling | skills/list 모두 repo scope, enabled |

Karpathy는 별도 Skill을 중복 설치하지 않고 원칙을 AGENTS.md에 통합했다. STE도 지침만 적용했다. 기존 Skill을 삭제·비활성화하지 않았다. explain_me와 prompts.chat은 설치하지 않았다.

## CONFIGURED

기존 [AGENTS.md](../AGENTS.md)의 원래 바이트를 접두부로 그대로 보존하고 운영 정책을 추가했다. [상세 정책](skill-policy.md)은 Superpowers 기본 과정, 선택적 EGM, 요청 기반 Archify, UI 전용 전문 지침, Karpathy4원칙, 한국어 STE 출력, 우선순위·중복·비용·보존 조건을 포함한다.

전역 Superpowers와 EGM은 다른 프로젝트에서도 목록에 노출될 수 있다. 이번 프로젝트 정책을 다른 프로젝트의 AGENTS.md에 복사하거나 전역 AGENTS.md를 수정하지 않았다. 전역 config는 승인한 plugins/marketplaces 섹션만 바뀌었다. 기존 플러그인 항목과 비플러그인 설정은 보존했다. 에이전트·모델·역할 설정은 바꾸지 않았다.

## VERIFIED

- Codex CLI0.160.0의 실제 app-server 프로토콜로 `skills/list`, `plugin/installed`, `plugin/read`, `plugin/skill/read`를 호출했다. 모델의 설명이나 단순 파일 존재만으로 인식을 판단하지 않았다. thread/turn 생성 요청은 보내지 않았다.
- 프로젝트 Skill8개가 오류 없이 enabled/repo로 인식됐다. 전역 플러그인은 설치 상태 전용 API에서 installed/enabled를 확인했다. 원격 카탈로그용 plugin/read summary만으로 설치 상태를 판정하지 않았다.
- Superpowers 실제 설치본의 using-superpowers, Codex 도구 안내, verification-before-completion을 읽었다. 메타데이터에서 핵심 계획·TDD·리뷰·완료 Skill을 확인했다. EGM 실제 발견 경로와7개 Skill을 확인했다. 두 플러그인의 조회 결과에 hooks/MCP 서버/추가 앱은 없었다.
- Archify 공식 설치 안내에 따라 `archify` 하나만 발견한 뒤 Codex 프로젝트 경로에 설치했다. `doctor`가 종료0과 `Archify is ready`를 반환했다. Node·템플릿·렌더러·스키마·안전 출력 런타임 진단이다.
- UI 로컬 검색에서 `keyboard focus --domain ux --max-results 1 --json`이 종료0, domain=ux/count=1/Issue=Focus States를 반환했다. 외부 요청·디자인 시스템 저장·실제 UI 변경은 하지 않았다.
- 설치 전 해시를 기록한 소스·테스트·마이그레이션·frontend·스크립트·설정63개가 모두 같았다. 아키텍처 문서의 기존 해시도 같았다. global config의 기존 비플러그인 설정과 기존 plugin 항목, AGENTS 원래 접두부를 별도로 비교했다.
- 구체 결과·버전·설치본 해시·발견 목록·범위는 [검증 artifact](../work/verification/2026-11-11-skills-installation.json)에 있다. 원격 아이콘 인증 URL과 전역 설정 원문은 artifact에 넣지 않았다.

## CONFLICTS

- Superpowers 저장소 개발본7.0.2와 공식 Codex 마켓플레이스7.0.1은 다르다. 승인한 공식 배포 경로의7.0.1을 설치했고 그 실제 본문을 기준으로 한다. 자동 업그레이드하지 않았다.
- UI 최신 npm 배포2.15.0은 README의 `--dry-run`을 지원하지 않는다. 실행 전 tarball을 `--ignore-scripts`로 받아 압축 내부 설치 코드와 대상 경로·건너뛰기 동작을 읽었다. 그 검토한 CLI를 `init --ai codex --offline`로 실행했고 --force는 쓰지 않았다. 개발 브랜치의 동작을 배포본 동작으로 단정하지 않았다.
- Archify는 공식 설치 안내가 지정한 skills1.7.6 설치기로 project/Codex/copy만 선택했다. 기존 archify 대상이 없음을 확인했다. 설치 명령에는 일회성 DISABLE_TELEMETRY=1을 사용했다. 프로젝트 환경 변수 파일은 수정하지 않았다. skills-lock.json은 공식 설치기가 추가한 패키지 추적 정보다.
- Superpowers의 설정 예시보다 기존 Sol/Luna·동시 한도·역할 보존과 실제 도구 스키마를 우선한다. 이번에 multi_agent나 reasoning 기본값을 추가하지 않았다. 현재 저장소에 최초 커밋이 없어 Git 기반 개발 흐름은 별도 확인이 필요하다.
- EGM의 영어 지시보다 사용자 한국어 요청을 우선한다. 필수 독립 검토를 같은 컨텍스트의 자기 검토로 대체하지 않는다.

## LIMITATIONS

설치 진단·Skill 발견·본문 접근을 실제 개발 워크플로 통과로 확대하지 않는다. EGM의 독립 컨텍스트/설계 검토, Superpowers의 구현·TDD·worktree·브랜치 마감은 실행하지 않았다. Archify의 다이어그램 finalize/browser-check, UI 실제 렌더링·접근성 검증도 실행하지 않았다. 제품 코드 테스트는 이번 설정 작업에서 실행하지 않았다.

호출 조건은 문서와 설치 메타데이터로 점검했다. LLM의 모든 미래 자동 라우팅이 보장된다는 의미는 아니다. 기존 대화의 Skill 목록은 다음 턴 또는 새 세션에서 갱신이 필요할 수 있다. Karpathy는 별도 호출 ID가 없는 프로젝트 지침이다.

## NEXT

다음 작업을 사용자가 지정하면 해당 조건에 맞는 Skill을 사용한다. 이번 설치가 다음 기능 착수 승인은 아니다. M2 보류는 유지한다. 사용자 선택 없이 설계 리뷰·시각화·UI 생성이나 에이전트 변경을 시작하지 않는다.
