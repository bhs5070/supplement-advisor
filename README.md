# 건강기능식품 구매 판단 도우미

> M2-A의 필수 코드 수정·관련 검사·독립 재검토를 마쳤습니다. 주간 한도에 따라 이번에는 인계까지 마감했습니다. 실행 중인 서비스는 M1이며, M2-A 실행 반영·실제 URL 검증은 다음 작업입니다. [현재 작업판](docs/tasks.md)과 [최종 검토](docs/reviews/m2a-review.md)를 확인하세요.


AI Agent Engineer 포트폴리오 프로젝트. M1은 비회원 제품 URL의 안전 수집과 수집 보고서 저장·조회 기능이다. 전체 제품 평가와 회원 개인화는 후속 마일스톤이다. 검증 상태는 `docs/verification.md`를 확인한다.

## 포트폴리오 요약

제품 URL에서 확인한 표시 정보와 공식 등록정보, 조사한 자료의 근거를 구분해 보여 주는 프로젝트다. 단순한 모델 응답 생성 외에 안전한 URL 수집, 호출 예산, 중단·재개, 권한 있는 결과 조회를 구현했다.

| 범위 | 현재 상태 |
|---|---|
| M1 수집·공식 대조·저장·조회·추가 정보 보완 | 한정 실연동 검증 완료. 사이트별 자동 추출·매칭 한계는 유지 |
| M2-A Supervisor·전문 역할·자료 조사·화면 | 구현 및 필수 수정의 독립 재검토 완료. 마지막 수정본의 전체 실PG 검사·배포·실URL 검증 대기 |
| 점수·구매 추천·회원 개인화 | 후속 범위 |

기술 구성과 설계 근거는 [아키텍처](docs/architecture.md), 검증 범위는 [검증 기록](docs/verification.md), 발표용 설명은 [포트폴리오 소개](docs/portfolio.md)를 확인한다. 개발 Agent의 협업과 서비스 내부의 조사 역할은 별개다.

## VS Code 터미널에서 구현 이어가기

이 저장소 폴더를 VS Code에서 연 뒤 통합 터미널에서 실행한다.

```bash
bash scripts/start-codex.sh --check
bash scripts/start-codex.sh
```

리드 Codex에게 합의한 설계와 팀 구현·독립 검증 루프를 읽고 첫 마일스톤을 이어가라는 시작 프롬프트를 전달한다. 개발 리드는 GPT-6.1 Sol, 서브에이전트 기본값은 GPT-6 Luna다. 서비스 내부에서 사용할 GPT-5.6 Luna와 개발용 Codex 모델 선택은 별개다.

VS Code의 **Terminal → Run Task → Codex: 팀 구현 이어가기**로도 시작할 수 있다. 이 저장소 자체를 작업 폴더로 열어야 한다. 현재 컴퓨터에는 Codex CLI가 설치되어 있으며 `code` 셸 명령은 PATH에서 확인되지 않았다. VS Code의 Open Folder로 폴더를 열면 된다.

다른 컴퓨터에서 CLI가 없으면 [공식 Codex CLI 안내](https://learn.chatgpt.com/docs/codex-cli)에 따라 설치하고 `codex login`으로 로그인한다. 실행 중 프로젝트 신뢰나 권한 설정은 CLI가 안내하는 내용을 확인한다. 실행 스크립트는 전역 설정이나 로그인 정보를 변경하지 않는다.

처음 시작하는 CLI 대화는 이 앱의 채팅 기록이나 이전 Agent의 메모리를 자동으로 인계받지 않는다. 대신 저장소의 `AGENTS.md`와 아래 인계 파일을 읽게 한다. 중단 후에는 `codex resume`의 선택 화면에서 해당 프로젝트 세션을 골라 이어갈 수 있다.

## 인계 자료

- `docs/handoff.md`: 실제 코드 상태, 미검증 범위, 다음 작업.
- `docs/product-scope.md`: 대화에서 확정한 제품·평가·실행 규칙.
- `docs/architecture.md`: 합의한 아키텍처 원본 사본.
- `docs/contracts.md`: 첫 기능의 HTTP·모듈 계약.
- `docs/tasks.md`: 마일스톤과 역할별 완료 기준.
- `AGENTS.md`: 작업 소유권, 독립 검증, Clean Code 리뷰 규칙.

OpenAI Docs의 [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)와 설치된 CLI 도움말을 확인해 실행 옵션을 구성했다. 실제 Agent 호출은 실행한 리드 세션이 작업 필요에 따라 수행한다.

## 로컬 실행

실행 작업공간: `/Users/hyeonseokbae/Desktop/ad_fact_check`. 현재 Docker 서비스가 실행 중이다.

```bash
cp .env.example .env
docker compose up --build -d
```

화면은 http://localhost:5173, API 문서는 http://localhost:8000/docs 에서 연다. API 시작 전에 초기 마이그레이션과 LangGraph PostgreSQL 체크포인트 테이블을 준비한다. `GET /api/ready`로 DB·Redis 연결을 확인한다. 외부 키가 없으면 수집 보고서는 해당 연동을 미설정으로 표시하며 제품 점수나 추천을 만들지 않는다.

```bash
uv sync --frozen --python 3.11
uv run pytest -q
cd frontend
npm ci
npm run build
```

PostgreSQL 전용 검사는 `TEST_DATABASE_URL`을 별도로 지정한다. 실행 데이터와 원문은 Docker 볼륨에 남는다. 비회원 조회 토큰은 URL이나 로그에 넣지 않으며 브라우저의 현재 세션에서만 사용한다.

외부 실연동을 검증하려면 로컬 `.env`의 `OPENAI_API_KEY`와 `FOOD_SAFETY_API_KEY`에 각 발급 키를 직접 입력한다. 키를 채팅·명령 인자·검증 로그에 붙여넣지 않는다. `.env`는 버전 관리에서 제외한다. 저장 후 `docker compose up -d --force-recreate api worker beat`로 실행 프로세스에 반영한다. `GET /api/capabilities`는 설정 유무만 알려 주며 키의 유효성이나 모델 접근 권한을 증명하지 않는다. 실제 호출 성공과 표시 정보·공식 제품 식별의 품질은 별도로 검증해야 한다. 기본 모델은 합의된 `gpt-5.6-luna`를 유지한다.

공개 페이지 소규모 검사는 `uv run python scripts/verify_product_quality.py --output work/verification/product-quality.json`으로 실행한다. 기본값은 외부키를 사용하지 않는다. 실제 모델·공식 API 호출을 허용하려면 `--use-configured-keys`를 명시한다. 수집·보고서 계약 통과와 추출·매칭 성공을 구분해 JSON의 checks와 quality assessment를 확인한다.

실제 prefork 프로세스 종료·hard-timeout 복구 검사는 `uv run python scripts/verify_process_recovery.py`로 별도 Compose project에서 실행한다. 두 시나리오가 기본 240초 lease 만료를 기다리므로 약 10분 걸린다. 테스트 스택만 종료하고 볼륨은 보존한다. 일반 pytest에서는 이 장시간 검사를 건너뛰며 `RUN_PROCESS_RECOVERY=1 uv run pytest tests/test_process_recovery_harness.py -q`로 명시 실행할 수 있다.


국내 소규모 식별 검사는 `uv run python scripts/verify_domestic_matching.py --output work/verification/domestic-matching.json`으로 실행한다. 기본값은 외부키를 사용하지 않으며 실호출은 `--use-configured-keys`가 필요하다. 원래 국내 표본 3개에서 2개 페이지·실모델 2건을 확인했지만 신고번호를 확보하지 못해 독립 공식 일치는 0건이었다. 검사 실행과 매칭 품질 충분 판정은 구분하며 최신 M1 종료 판정은 `docs/tasks.md`를 확인한다.

화면 자동 검사는 `cd frontend && npm run test:e2e`로 실행한다. 최초 환경에서는 `npx playwright install chromium`이 필요하다. 전용 포트 5174에서 이 checkout의 Vite를 시작하며 기존 서버를 재사용하지 않는다. 실제 Chromium과 mock API를 사용하는 개발 테스트로, 실모델·공식 API 검증과 구분한다. 정상 보고서의 desktop/mobile 캡처는 `frontend/work/verification/normal-desktop-report.png`, `normal-mobile-report.png`에 저장된다.


M1에는 권한 있는 비회원의 추가 정보 1회 보완을 포함한다. 정보 부족 보고서에서 알고 있는 제품명·제조사·신고번호와 선택 수동 성분을 한 묶음으로 제출하면 기존 보고서를 기반으로 공식 등록을 재대조한다. 사용자 입력과 판매 페이지 출처를 나누어 표시하고 기존 실행 예산을 초기화하지 않는다. 수동 성분 목록은 기존 목록을 대체하며 없는 값은 미확인으로 남긴다. 회원·이미지 판독·전체 제품 평가는 포함하지 않는다. 최신 실통합 상태는 `docs/verification.md`에서 확인한다.

공식 후보 자동 대조는 페이지에 신고번호가 없어도 제품명·제조사로 제한된 검색을 하고 실제 표시 성분과 비교합니다. `공식 등록 확인`, `후보 있음`, `미확인`을 구분하며 공식 번호를 페이지에서 읽은 번호처럼 채우지 않습니다. 검색 결과가 불완전하거나 동일 조건의 신고가 여러 건이면 후보로 남깁니다. 최신 cached 국내 실API 표본은 자동 확인0/후보1/미확인1(기존 수집실패1 별도)로, 후보 검색 개선은 확인했지만 URL 자동 확정 목표는 아직 달성하지 못했습니다. 정확한 최종 결과·한계는 `docs/verification.md`를 확인합니다.

M1은5사이트 고정20URL로 한정 평가했습니다. HTML16개를 수집했고 SSG4개는 HTTP오류였습니다. 사이트 전체의 성공을 보장하지 않으며, 명시된 제품명·제조 역할·등록 근거가 있는 공개 HTML을 지원 조건으로 삼습니다. 누락·이미지 의존·모호한 후보는 미확인으로 남깁니다. 원래 평가 분모, 후속 guard 수정과 검증 한계는 [M1 평가 결과](docs/evaluation/m1-results.md)에 구분해 기록합니다.

사용자의 이후 “M2 시작하자” 지시로 M2 보류를 해제했습니다. 현재 기존 코드·계약 조사와 첫 구현 순서 선택 단계이며 제품 코드 구현 전입니다. M1 한정 평가와 마지막 guard 검증 결과는 보존합니다. 최신 진행은 [M2 착수 기록](docs/m2-kickoff.md)을 확인합니다.
