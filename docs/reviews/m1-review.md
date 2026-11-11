# M1 독립 검증·Clean Code 리뷰

검증자: 구현 파일을 작성하지 않은 `independent_qa` Agent. 2026-11-07.
대상: URL 접수 → 수집 → LangGraph → 저장·비회원 권한 조회와 개발 환경.
리뷰 원칙: `AGENTS.md`의 최소 완결 변경·호출부/데이터 흐름/오류 처리·입력 경계 보존.
제품 코드는 검증자가 수정하지 않으며 필수 수정은 구현 담당자가 수행한다.

## 1차 판정: 필수 수정 대기

### R1. 실제 Worker 시간 상한과 선예약 시간이 다름 — 필수

- 위치: `src/supplement_advisor/tasks.py`의 `asyncio.timeout(window)`와 동기 `reserve_call`/`checkpoint`/`store_html`, `celery_app.py`의 soft 70초·hard 80초.
- 재현 조건: HTML 저장이나 동기 DB 호출이 60초보다 오래 걸리는 경우 `asyncio.timeout(60)`은 이벤트 루프가 다시 실행될 때까지 취소를 전달하지 못한다. 이 상태에서 Worker를 80초 hard limit에 도달시키고 lease 만료 후 재점유한다.
- 영향: 작업마다 60초를 예약하지만 실제 실행은 최대 80초일 수 있어 3회 복구 시 180초 계약을 초과할 수 있다. queue 대기 제외·예산 영속화 자체는 구현되어 있으나 실제 실행 시간 제한과 맞지 않는다.
- 가장 작은 수정안: 예약 window와 Celery의 실제 hard limit을 일치시키고 soft limit은 그보다 작게 둔다. 동기 I/O 경계를 별도 처리해 API/Worker 이벤트 루프를 막지 않도록 한다. 낮춘 설정에서도 동일한 관계가 유지되어야 한다. 수정 후 장애 시나리오와 제한 설정을 함께 검증한다.

### R2. 긴 조회 토큰이 404가 아닌 422를 반환 — 필수

- 위치: `src/supplement_advisor/main.py`의 조회 함수 `Header(max_length=256)`.
- 재현: 정상 접수한 id에 `X-Analysis-Token`을 `x` 257자로 보내면 422, 짧은 잘못된 토큰은 404.
- 영향: 잘못된 id/토큰은 동일 404라는 공개 계약과 다르다.
- 가장 작은 수정안: 토큰 길이를 조회 함수의 안전한 조기 검사에서 처리하고 동일 404를 반환한다. 입력 원문을 에러 응답에 포함하지 않는다.
- 독립 재현: `tests/test_review_regressions.py::test_oversized_guest_token_has_same_not_found_response` 실패 확인.

### R3. 쉼표가 포함된 함량의 일부 숫자를 실제 함량으로 보존 — 필수

- 위치: `src/supplement_advisor/agents/collection_graph.py`의 `_ground_extraction` amount 경계 정규식.
- 재현: 원문 `비타민C 1,000 mg`에 모델이 amount `1` 또는 `000`을 반환하면 둘 다 보존된다.
- 영향: 원문 1,000 mg을 1 mg 또는 000 mg으로 바꿔 표시하므로 없는 함량을 만들지 않는 계약을 위반한다.
- 가장 작은 수정안: 함량 숫자의 토큰 경계에 쉼표 등 숫자 표기를 포함해 부분 값은 거부하고 완전한 원문 표기는 보존한다. 단위 변환이나 추정은 하지 않는다.
- 독립 재현: `test_thousands_separator_does_not_turn_amount_substring_into_value`의 두 사례 실패 확인.

### R4. 접수의 동기 발행/DB가 API 이벤트 루프를 막음 — 필수

- 위치: `src/supplement_advisor/main.py`의 async `submit` 안 동기 Session·`publish(analysis_id)`.
- 재현: broker 발행이 0.5초 대기하는 동안 같은 이벤트 루프의 다른 coroutine이 0.02초 뒤 진행하지 못한다.
- 영향: Redis 장애나 DB 지연 시 하나의 접수가 health·조회·다른 접수를 모두 멈추게 한다. 비동기 URL 검증을 사용하는 FastAPI 흐름과 맞지 않는다.
- 가장 작은 수정안: DB 저장·발행처럼 동기인 경계를 FastAPI/Starlette의 표준 threadpool로 실행한다. 무한 executor나 별도 추상화 계층을 만들 필요는 없다. DB/Redis 자체 timeout도 제한한다.
- 독립 재현: `test_broker_publication_does_not_block_the_api_event_loop`.

### R5. IPv6 site-local 주소를 공개 주소로 허용 — 필수

- 위치: `src/supplement_advisor/collection.py`의 `_public_ip`.
- 재현: Python 3.11에서 `fec0::1`의 `is_global=True`, `is_private=False`, `is_reserved=False`, `is_site_local=True`이다. 현재 `validate_public_url("http://[fec0::1]/")`가 허용된다.
- 영향: deprecated된 범위여도 site-local `fec0::/10` 내부 주소에 접속할 수 있어 공개 인터넷 수집 경계를 벗어난다.
- 가장 작은 수정안: IPv6의 `is_site_local`을 명시적으로 거부한다. 주소를 실제로 요청하지 않고 검증 경계에서 거부하는 독립 회귀를 추가했다.
- 독립 재현: `test_ipv6_site_local_address_is_not_public`.

## 독립 실행 증거

| 명령/범위 | 구분 | 결과 |
|---|---|---|
| `.venv/bin/python -m pytest tests/test_collection.py tests/test_repository.py -q` | 수집 mock + SQLite DB | 44 passed, 16 skipped (PG 환경변수 미설정) |
| `TEST_DATABASE_URL=... .venv/bin/python -m pytest tests/test_repository.py -q --tb=short` | 실제 PostgreSQL 17 | 29 passed, 1 skipped (SQLite에서만 PG row-lock 전용 검사 제외) |
| `.venv/bin/python -m pytest tests/test_api_worker.py tests/test_agents.py -q --tb=short` | SQLite 통합 + 모델/공식 API mock | 22 passed |
| `.venv/bin/python -m pytest tests/test_review_regressions.py -q --tb=short` | 독립 계약/근거 경계 재현 | 4 failed: R2 한 사례, R3 두 사례, R4 한 사례 |

첫 PG 실행은 sandbox의 localhost TCP 제한으로 실패했다. 승인된 실행으로 재수행한 29 passed가 실제 PostgreSQL 결과다. 네트워크 제한 실패를 제품 코드 실패나 실연동 통과로 세지 않았다.

수집기의 public IP 고정·TLS SNI·리디렉션마다 DNS 재검증·프록시 배제·크기 제한과 DB의 claim fencing·lease 만료·row-lock 대기 후 재확인은 구현을 확인했다. 수집 주소 경계의 site-local 누락은 R5로 별도 기록했다. 이는 테스트한 경계 내 판정이며 실사이트 전체 수집률이나 제품 매칭 정확도 증명을 의미하지 않는다.

## 남은 검증

- 담당 구현자의 필수 수정 후 독립 회귀 재실행 및 최종 코드 버전 식별.
- 완성된 프런트엔드의 토큰 보관·polling/에러·M1 표현·접근성 검토.
- 실제 Redis/Celery/HTTP/Graph checkpoint/원문 파일/권한 조회 및 crash 복구 경로는 리드의 실연동 증거와 함께 대조.
- API 키가 없어 OpenAI 모델 및 FoodSafety I0030 실제 인증 응답·품질은 미검증. 모의 응답 성공과 구분한다.
- 사용자 지정 `Desktop/ad_fact_check` 복사본에서 실행·검증 일치 확인.

## 최종 독립 재검증 — 수정 통과

검증자: 최초 지적자와 구현 담당자에서 분리된 `independent_qa`. 2026-11-07.

| 지적 | 확인한 수정 | 독립 결과 |
|---|---|---|
| R1 | 실행 시도 창을 선예약하고 `process_analysis` task annotation의 hard limit을 같은 창으로, soft limit을 1초 낮게 적용. 설정 기본값(시도 60초, 전체 180초)에서 Celery task 객체를 finalize한 뒤 검사 | `time_limit=60`, `soft_time_limit=59`; 전역 기본 80/70초보다 task별 제한이 실제 적용됨. 3회 예약 합계는 최대 180초. |
| R2 | 조회 토큰 길이 초과를 함수 내에서 404 처리 | 회귀 검사에서 짧은 오토큰과 257자 토큰이 같은 404 응답 |
| R3 | 금액 정규식의 숫자 경계에서 쉼표·소수점·부호에 걸친 부분 일치를 거부 | `1`/`000`은 null로 거부. 완전 표기 보존 검사는 구현 담당자의 별도 검사 결과에 포함 |
| R4 | 접수 DB 저장과 broker 발행을 Starlette threadpool로 실행 | 동기 broker 대기 중 concurrent coroutine 진행 회귀 통과 |
| R5 | IPv6 `is_site_local`을 public IP에서 제외 | `fec0::1`을 실제 접속 없이 URL 검증 단계에서 거부 |

독립 실행:

| 명령 | 결과 |
|---|---|
| `./.venv/bin/python -m pytest tests/test_review_regressions.py -q --tb=short` | 5 passed (R2, R3 부분값 2종, R4, R5) |
| `./.venv/bin/python -c 'from supplement_advisor.celery_app import celery_app; from supplement_advisor.tasks import process_analysis; celery_app.finalize(); print(process_analysis.time_limit, process_analysis.soft_time_limit); print(celery_app.conf.task_time_limit, celery_app.conf.task_soft_time_limit, celery_app.conf.task_annotations)'` | task 객체 `60 59`; 전역 기본 `80 70`, 이름 기반 annotation 적용 확인 |

구현 담당자의 별도 검사 결과는 `tests/test_review_regressions.py`, collection/agents/API-worker 검사를 합쳐 64 passed 및 Ruff 통과로 전달받았다. 이는 독립 실행과 구분한다. hard-timeout 도중 실제 Worker kill/recovery, Desktop 최종 복사본, 실제 모델·공식 조회는 이 재검증에 포함되지 않았다. 실제 Docker live/recovery HTTP 검증은 리드가 별도로 수행한다.

검증 코드 버전 SHA-256:

| 파일 | SHA-256 |
|---|---|
| `src/supplement_advisor/main.py` | `3dd8b358cfc5a44f7ef4b8e8aefa85b3b3aa2e04afa46f1596be55a745e750d5` |
| `src/supplement_advisor/tasks.py` | `e3cd06790d2b9907d44b7efe4edfee0251a642a4424974bfb70243da249102d2` |
| `src/supplement_advisor/celery_app.py` | `4309bb5a04afb738287a825292c81d76cf941bb0db288c6d01aa6e2c16b9cf51` |
| `src/supplement_advisor/collection.py` | `42f1d5bd368ea88435e41667b543ba397de1ac53b97e3c94984412682d528630` |
| `src/supplement_advisor/agents/collection_graph.py` | `219a26f914581dbcb9fa801bbbbea4408a928fc688d8e24d5867c4f9939717e9` |
| `tests/test_review_regressions.py` | `148de202200dc19c2f2033faf786e100c94bd57114230e86ef7d0f79ba35e826` |

## 문서 계약 검토 메모

최초 문서 검토 시점에는 동기화할 역사적 불일치가 있었다. `docs/tasks.md`는 독립 지적을 R1–R4로만 열거하고 R5를 빠뜨렸으며, `docs/handoff.md`의 발견 요약도 R2/R3/R1로만 적어 R4/R5를 빠뜨렸다. `docs/verification.md`는 R1–R5 수정 진행 중이라고 남아 있었다. 이후 리드가 이 세 문서를 수정했다고 전달받았다. `.codex/config.toml`, `scripts/start-codex.sh`, `README.md`, `docs/contracts.md`에서는 이번 코드 수정과 충돌하는 개발 모델 또는 M1 계약을 발견하지 않았다. 이 검증 보고서 외 문서는 소유권 지침에 따라 수정하지 않았다.
