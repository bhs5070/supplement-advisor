# Supplement Advisor

**LangGraph Supervisor 기반 건강기능식품 근거 조사 Multi-Agent 시스템**

![LangGraph](https://img.shields.io/badge/Agent-LangGraph%20StateGraph-1C3C3C)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-149ECA?logo=react&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-4169E1?logo=postgresql&logoColor=white)

제품 URL을 입력하면 **Supervisor Agent가 조사할 전문 역할과 질문을 선택**하고, 선택된 역할이 공식 자료·논문 검색 도구를 사용해 근거를 조사합니다. 조사 결과를 취합한 뒤 Supervisor가 재조사 또는 종료를 결정하며, 출처와 원문 인용을 연결한 보고서를 생성합니다.

핵심은 **역할 선택 → 도구 사용 → 결과 관찰 → 재지시·종료**로 이어지는 Agent 실행 루프입니다. 이 흐름에 호출 예산, 상태 저장·복구, 근거 검증, 조회 권한을 연결해 구현했습니다.

---

## 프로젝트 배경

건강기능식품의 판매명은 공식 등록명과 다를 수 있고, 판매 페이지에는 성분·함량·제조 정보와 광고 문구가 섞여 있습니다. 일반적인 원료 연구가 특정 완제품의 효과를 입증하는 것처럼 해석되기도 합니다.

Supplement Advisor는 페이지에 적힌 정보와 공식 대조 결과, 외부 조사 자료를 분리해 보여 줍니다. 자료가 부족하면 추정으로 채우는 대신 확인되지 않은 항목을 남기도록 설계했습니다.

---

## Agent 시스템 설계

### Supervisor와 전문 역할

Supervisor가 제품 정보와 조사 필요성을 바탕으로 역할과 질문을 선택합니다. 각 역할은 검색·자료 조회·종료 중 다음 행동을 구조화 응답으로 결정합니다.

| 역할 | 담당 내용 |
|---|---|
| Supervisor | 조사 범위와 역할 선택, 결과 취합 후 재조사·종료 판단 |
| 성분·함량 표시 | 표시된 성분, 함량, 섭취 기준 확인 |
| 기능성·광고 근거 | 기능성 문구와 공식 자료·논문 근거 대조 |
| 개인 적합성 | 비회원은 미평가로 처리 |
| 안전성 | 일반적인 주의사항과 확인되지 않은 조건 조사 |
| 공식 정보·품질 | 공식 등록·표시 대조에서 확인한 범위 정리 |

비회원의 개인 적합성은 모델 호출 없이 미평가로 처리합니다. 나머지 네 전문 역할 중 필요한 역할을 선택하며, 실행하지 않은 역할의 사유도 결과에 남깁니다.

### 도구를 사용하는 조사 루프

조사 그래프는 실제 LangGraph `StateGraph`의 `supervisor`, `dispatch`, `aggregate`, `report` 노드와 조건부 분기로 구성했습니다.

1. **Supervisor:** 수집한 제품 정보와 기존 조사 결과로 역할·질문을 선택합니다.
2. **Dispatch:** 선택한 전문 역할을 최대 3개까지 동시에 실행합니다.
3. **전문 역할:** 모델이 다음 action을 선택하고, 런타임이 도구를 실행합니다. 조회 결과를 다시 모델 입력으로 전달해 다음 행동을 결정합니다.
4. **Aggregate:** 역할별 결과와 출처를 중앙 상태에 병합합니다.
5. **재지시·종료:** Supervisor가 결과를 확인해 다시 역할을 배정하거나 보고서 생성으로 종료합니다.

전문 역할이 선택할 수 있는 action은 다음과 같습니다.

| Action | 역할 |
|---|---|
| `search_official(query)` | 공식 문서 후보 검색 |
| `search_literature(query)` | 논문·초록 검색 |
| `fetch_source(source_id)` | 등록된 출처의 문서 조회 |
| `finish(result)` | 역할의 조사 결과 제출 |

행동은 OpenAI Structured Outputs로 반환하고, 허용된 역할·도구 이름과 입력 형식을 Pydantic으로 검증합니다. 임의 URL이나 등록되지 않은 source ID를 모델이 직접 실행하도록 두지 않습니다.

### Agent 판단과 실행 제어

| 모델이 결정하는 내용 | 런타임이 검증·제어하는 내용 |
|---|---|
| 어떤 전문 역할에 무엇을 물을지 | 고정 역할 목록, 동시 실행 수, 재지시 한도 |
| 다음에 어떤 자료를 조회할지 | 허용 도구·입력, 공개 URL·DNS 검증 |
| 확보한 근거를 어떻게 설명할지 | source ID·원문 인용·원료/제품 적용 범위 |
| 역할을 끝내거나 다시 조사할지 | 시간·요청 예산, 상태 저장, 복구 조건 |

역할의 질문·진행 상태·다음 행동·출처·사용량을 snapshot으로 저장합니다. 모델이 오류를 내거나 실행이 중단돼도, 확인하지 않은 내용을 성공으로 채우지 않고 조사한 범위의 부분 결과를 보존합니다.

---

## 주요 기능

### 1. 제품 정보 추출·공식 등록 대조

- 공개 제품 페이지에서 제품명, 제조사, 신고번호, 성분·함량과 광고 문구 추출
- 명시된 제품정보 표의 직접 추출과 LLM 구조화 추출을 함께 사용
- 식품안전나라 API로 신고번호 또는 제품명·제조사 기반 후보 조회
- 신고번호·제조사·주요 원료와 비교 가능한 함량을 대조하고, 판매명과 등록명 차이 표시
- 확정 대조, 후보, 미확인을 구분하고 페이지 정보와 공식 자료의 출처를 별도로 보존

### 2. 출처·인용 검증

- Tavily로 공식 문서 후보를 검색하고 Europe PMC·PubMed로 문헌 조회
- 검색 결과, 초록, 문서 본문의 조회 범위를 구분
- 결과의 source ID가 실제 등록된 출처인지 확인하고 인용문이 원문에 포함되는지 검증
- PMID·DOI 기반 중복 제거와 초록에서 본문으로의 출처 승격 처리
- 일반 원료 자료를 완제품 적용 근거로 확대하지 않도록 제한

### 3. Agent 실행 예산·장애 복구

FastAPI가 요청을 저장하고 Celery Worker가 분석을 수행합니다. Redis를 작업 전달에 사용하고, 작업 상태·보고서·복구 snapshot은 PostgreSQL에 저장합니다.

| 실행 제어 | 기본 한도 |
|---|---|
| 누적 활성 시간 | 180초 |
| 한 시도의 실행 창 | 60초 |
| 최대 실행 시도 | 3회 |
| 외부 요청 예약 | 수집·모델·자료 조회를 합쳐 총 20회 |
| 전문 역할별 요청 | 6회 |
| 동시 전문 역할 | 최대 3개 |
| Supervisor 재지시 | 총 2회, 같은 역할 1회 |

요청 전에 예산과 진행 표식을 저장하고, 유효한 claim·lease를 가진 Worker만 상태를 갱신합니다. 다음 작업을 시작할 시간이 부족하면 부분 결과를 저장해 대기열로 돌립니다. 결과가 불명확한 요청은 자동으로 반복하지 않습니다.

### 4. 토큰 기반 결과 조회·추가 정보 보완

- 분석별 조회 토큰을 발급하고 토큰 해시만 DB에 저장
- 토큰이 없거나 다른 경우 결과 조회를 404로 처리
- 식별 정보가 부족하면 제품명·제조사·신고번호·성분을 한 번 보완
- 보완된 사용자 정보와 판매 페이지 정보의 출처를 구분
- 기존 실행 예산과 보완 사용 이력을 유지하며 공식 등록정보 재대조
- React 화면에서 기초 제품 정보, 역할별 결과, 인용·출처, 미평가 항목 표시

---

## 시스템 아키텍처

```text
React / TypeScript
        │  제품 URL 제출 · 결과 조회
        ▼
FastAPI ───────────────────── PostgreSQL
        │                     요청 · 보고서 · 예산 · snapshot
        ▼                              ▲
Redis → Celery Worker ──────────────────┘
             │
             ├── 수집 그래프
             │     ├── HTTPX 공개 페이지 수집
             │     ├── 제품정보 표 / LLM 구조화 추출
             │     └── 식품안전나라 등록 대조
             │
             └── 조사 그래프 (사용자 선택)
                   ├── Supervisor → Dispatch → 전문 역할
                   │       ▲                    │
                   │       └──── Aggregate ─────┘
                   ├── Supervisor 종료 → Report
                   ├── Tavily 공식 자료 검색
                   └── Europe PMC / PubMed 문헌 조회
```

URL 수집은 HTTP(S) 공개 주소만 허용합니다. 내부 IP·메타데이터 주소 접근을 차단하고, 리디렉션마다 URL·DNS를 재검증합니다. 출처는 React 텍스트로 렌더링하며 외부 링크는 허용된 HTTP(S) 주소만 표시합니다.

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | React, TypeScript, Vite, CSS |
| Backend | Python, FastAPI, Pydantic, Uvicorn |
| Agent | LangGraph StateGraph, OpenAI Structured Outputs |
| 비동기 작업 | Celery, Redis |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| 페이지 수집 | HTTPX, 공개 URL·DNS·리디렉션 검증 |
| 외부 자료 | 식품안전나라 API, Tavily, Europe PMC, PubMed |
| 검증 | pytest, Ruff, Playwright Chromium |
| 실행 환경 | Docker Compose, uv, npm |

---

## 시작하기

### 사전 요구사항

- Git, Docker Compose
- 모델 추출·조사: OpenAI API 키
- 공식 등록 대조: 식품안전나라 API 키
- 공식 문서 검색: Tavily API 키

### 설치·실행

```bash
git clone https://github.com/bhs5070/supplement-advisor.git
cd supplement-advisor

cp .env.example .env
# .env에 사용할 연동의 API 키 입력

docker compose up --build -d
```

| 주소 | 용도 |
|---|---|
| http://localhost:5173 | 제품 URL 입력·분석 결과 화면 |
| http://localhost:8000/docs | API 문서 |
| http://localhost:8000/api/ready | PostgreSQL·Redis 연결 확인 |

Compose가 DB migration과 수집 그래프의 PostgreSQL 체크포인트 테이블을 준비합니다. 외부 키가 없는 기능은 미설정으로 표시합니다. 설정 여부는 `/api/capabilities`에서 확인할 수 있습니다.

### 환경 변수

| 변수 | 용도 |
|---|---|
| `OPENAI_API_KEY` | 모델 기반 구조화 추출·조사 |
| `OPENAI_MODEL` | 모델 선택. 기본값은 `.env.example` 참고 |
| `FOOD_SAFETY_API_KEY` | 식품안전나라 공식 등록정보 조회 |
| `TAVILY_API_KEY` | 공식 문서 후보 검색 |
| `DATABASE_URL` | PostgreSQL 연결 |
| `REDIS_URL` | 작업 broker 연결 |
| `RAW_STORAGE_DIR` | 수집 원문 저장 경로 |

Compose는 컨테이너의 DB·Redis·원문 저장 경로를 지정합니다. `.env`, 원문, 실행 산출물과 DB 파일은 Git에서 제외합니다.

---

## API

| Method | Endpoint | 기능 |
|---|---|---|
| POST | `/api/analyses` | 제품 분석 접수 |
| GET | `/api/analyses/{analysis_id}` | 조회 토큰을 사용한 결과 조회 |
| POST | `/api/analyses/{analysis_id}/supplement` | 추가 정보 한 묶음 제출 |
| GET | `/api/capabilities` | 외부 연동 설정 상태 조회 |
| GET | `/api/health` | API 상태 확인 |
| GET | `/api/ready` | DB·Redis 연결 확인 |

```json
{
  "url": "https://example.com/product",
  "mode": "evidence_review"
}
```

`mode`를 생략하면 제품 정보 수집·공식 대조를 수행합니다. `evidence_review`는 식별 정보가 확보된 후 근거 조사를 이어갑니다. 결과 조회와 보완 요청에는 `X-Analysis-Token` 헤더를 사용합니다.

---

## 검증

| 검사 | 확인 내용 |
|---|---|
| 기능·계약 | 역할 선택, 구조화 응답, 정보 보완, 출처·인용 검증 |
| 저장·복구 | claim·lease fencing, 경쟁 요청, 예약 보존, 중단 후 재요청 차단 |
| PostgreSQL | 격리 schema에서 migration·동시성·저장 동작 확인 |
| Chromium | API fixture 기반 데스크톱·모바일 결과 표시, 권한 오류, 보완 흐름 |
| 실제 연동 | 한정된 제품 URL의 수집·공식 대조·저장·권한 조회 확인 |

국내 5개 사이트의 고정 URL 20개로 수집·식별을 평가하고 실패 표본도 함께 기록했습니다. 전문 역할 조사는 구현 및 모의 모델·DB·브라우저 검사와 독립 검토를 수행했으며, 마지막 수정본의 전체 PostgreSQL 재검증과 모델·검색을 포함한 통합 실연동은 별도로 확인할 범위입니다. 상세 실행 버전과 결과는 [검증 기록](docs/verification.md)과 [수집 평가 결과](docs/evaluation/m1-results.md)에 있습니다.

### 개발 환경 검사

Python 3.11과 uv, Node.js가 필요합니다.

```bash
uv sync --frozen --python 3.11
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests migrations scripts/verify_research_live.py

cd frontend
npm ci
npx playwright install chromium
npm run test:e2e
npm run build
```

실제 PostgreSQL 검사는 `TEST_DATABASE_URL`을 지정하면 전용 schema에서 수행합니다. 일반 테스트와 화면 검사는 외부 모델·검색 호출의 성공률이나 제품 판정 정확도를 의미하지 않습니다.

---

## 프로젝트 구조

```text
supplement-advisor/
├── src/supplement_advisor/
│   ├── main.py                 # 접수·조회·보완 API
│   ├── tasks.py                # Worker 실행·복구
│   ├── collection.py           # 안전한 공개 페이지 수집
│   ├── repository.py           # 조건부 상태 갱신·예산·snapshot 저장
│   ├── models.py               # 분석 데이터 모델
│   └── agents/
│       ├── collection_graph.py # 수집·추출·공식 대조
│       ├── research_graph.py   # Supervisor·전문 역할 조사
│       ├── evidence_tools.py   # 공식 자료·문헌 조회
│       └── research_types.py   # 결과 스키마·출처·인용 검증
├── frontend/                   # React 화면·Playwright 검사
├── migrations/                 # Alembic DB migration
├── scripts/                    # 평가·실연동·복구 검증 도구
├── tests/                      # 기능·계약·회귀·통합 검사
├── docs/                       # 설계·기술 판단·검증 기록
└── compose.yaml                # 로컬 서비스 구성
```

## 관련 문서

- [아키텍처와 역할 구성](docs/architecture.md)
- [API·저장·실행 계약](docs/contracts.md)
- [근거 조사 설계](docs/superpowers/specs/2026-11-11-m2a-evidence-review-design.md)
- [검증 기록](docs/verification.md)
- [수집·식별 평가](docs/evaluation/m1-results.md)

---

**배현석 (Hyeonseok Bae)** · [GitHub @bhs5070](https://github.com/bhs5070)
