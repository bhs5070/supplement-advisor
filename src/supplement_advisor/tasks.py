"""Fenced worker execution and the durable queued/expired-job recovery scan."""

import asyncio
import time
from types import SimpleNamespace

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from .agents import run_collection_graph
from .celery_app import celery_app
from .collection import CollectionError, collect_page
from .config import Settings, get_settings
from .database import make_engine, session_factory
from .repository import (
    claim_analysis,
    finish_analysis,
    get_analysis,
    list_dispatchable,
    reserve_budget,
    save_snapshot,
    save_worker_state,
    yield_analysis,
)
from .storage import store_html


async def execute_analysis(analysis_id: str, settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    sessions = session_factory(engine)
    try:
        with sessions() as session:
            analysis = claim_analysis(session, analysis_id)
            session.commit()
            if analysis is None:
                return
            claim_token = analysis.claim_token
            assert claim_token is not None
            url, product_name = analysis.url, analysis.product_name
            mode = analysis.mode
            snapshot = analysis.graph_snapshot
            stored_report = analysis.report
            supplemental_input = analysis.supplemental_input
            received_at = analysis.supplemental_received_at
            original_raw_file = analysis.raw_file

        def reserve_call(seconds: float, tool_calls: int) -> bool:
            # The whole attempt window is already charged. Only charge calls here.
            with sessions() as session:
                accepted = reserve_budget(
                    session,
                    analysis_id,
                    claim_token=claim_token,
                    seconds=0,
                    tool_calls=tool_calls,
                    max_seconds=settings.analysis_timeout_seconds,
                    max_tool_calls=settings.max_tool_calls,
                )
                session.commit()
                return accepted

        def checkpoint(value: dict) -> None:
            with sessions() as session:
                saved = save_snapshot(session, analysis_id, claim_token=claim_token, snapshot=value)
                session.commit()
                if not saved:
                    raise RuntimeError("The work lease is no longer valid")

        window = min(settings.attempt_timeout_seconds, settings.analysis_timeout_seconds)
        with sessions() as session:
            reserved = reserve_budget(
                session,
                analysis_id,
                claim_token=claim_token,
                seconds=window,
                tool_calls=0,
                max_seconds=settings.analysis_timeout_seconds,
                max_tool_calls=settings.max_tool_calls,
            )
            session.commit()
        status, report, raw_file, error_code, message = "failed", None, original_raw_file, None, None
        yielded_to_queue = False
        envelope = None

        def interrupted_collection_report(collection_report):
            from .agents.research_types import (
                ResearchResult,
                RoleResult,
                personal_fit_not_applicable,
            )

            with sessions() as db:
                current = get_analysis(db, analysis_id)
                reserved_calls = current.tool_calls_reserved if current is not None else 0
            roles = [
                RoleResult(
                    role=role, status="insufficient_evidence", question="",
                    reasons=["unknown_interrupted"],
                )
                for role in ("composition", "claims", "safety", "official_quality")
            ]
            roles.insert(2, personal_fit_not_applicable())
            research = ResearchResult(
                status="partial", roles=roles, sources=[],
                limitations=["수집 요청이 중단되어 결과를 확인할 수 없습니다."],
                termination_reason="unknown_interrupted", decisions=[],
                usage={"total": reserved_calls, "by_role": None, "attribution": "unavailable"},
            ).model_dump()
            return {
                "scope": "evidence_review", "collection_report": collection_report,
                "score": None, "verdict": "hold", "research": research,
            }

        if not reserved:
            error_code, message = "budget_exhausted", "누적 실행 한도에 도달했습니다."
        else:
            worker_started = time.monotonic()
            runtime = SimpleNamespace(
                openai_api_key=settings.openai_api_key,
                openai_model=settings.openai_model,
                food_safety_api_key=settings.food_safety_api_key,
                external_timeout_seconds=settings.external_timeout_seconds,
                model_timeout_seconds=settings.model_timeout_seconds,
                tavily_api_key=settings.tavily_api_key,
                analysis_timeout_seconds=window,
                max_tool_calls=settings.max_tool_calls,
                reserve_budget=reserve_call,
                save_snapshot=checkpoint,
                graph_snapshot=snapshot,
            )
            try:
                async with asyncio.timeout(window):
                    if mode == "evidence_review":
                        from .agents import run_research_graph

                        envelope = snapshot if isinstance(snapshot, dict) else None
                        if envelope is not None and (
                            envelope.get("version") != 1
                            or envelope.get("mode") != "evidence_review"
                            or not {"collection_snapshot", "collection_report", "research_snapshot"}
                            <= envelope.keys()
                        ):
                            from .agents.research_types import (
                                ResearchResult,
                                RoleResult,
                                personal_fit_not_applicable,
                            )

                            prior_m1 = stored_report
                            if isinstance(prior_m1, dict) and prior_m1.get("scope") == "evidence_review":
                                prior_m1 = prior_m1.get("collection_report")
                            if not isinstance(prior_m1, dict):
                                prior_m1 = {}
                            with sessions() as db:
                                current = get_analysis(db, analysis_id)
                                reserved_calls = current.tool_calls_reserved if current is not None else 0
                            fallback_roles = [
                                RoleResult(
                                    role=role,
                                    status="insufficient_evidence",
                                    question="",
                                    reasons=["snapshot_invalid"],
                                )
                                for role in ("composition", "claims", "safety", "official_quality")
                            ]
                            fallback_roles.insert(2, personal_fit_not_applicable())
                            fallback_research = ResearchResult(
                                status="partial",
                                roles=fallback_roles,
                                sources=[],
                                limitations=["조사 상태를 복원할 수 없어 근거 검토를 완료하지 못했습니다."],
                                termination_reason="snapshot_invalid",
                                decisions=[],
                                usage={
                                    "total": reserved_calls,
                                    "by_role": None,
                                    "attribution": "unavailable",
                                },
                            ).model_dump()
                            report = dict(prior_m1)
                            report.update({
                                "scope": "evidence_review", "collection_report": dict(prior_m1),
                                "score": None, "verdict": "hold",
                                "research": fallback_research,
                            })
                            status = "completed"
                        else:
                            if envelope is None:
                                envelope = {
                                    "version": 1, "mode": "evidence_review",
                                    "collection_snapshot": None, "collection_report": None,
                                    "research_snapshot": None,
                                }

                            def save_m2_state(*, updated_report=None, updated_raw_file=None):
                                with sessions() as db:
                                    saved = save_worker_state(
                                        db, analysis_id, claim_token=claim_token,
                                        snapshot=envelope, report=updated_report,
                                        raw_file=updated_raw_file,
                                    )
                                    db.commit()
                                    if not saved:
                                        raise RuntimeError("The work lease is no longer valid")

                            def collection_checkpoint(value):
                                envelope["collection_snapshot"] = value
                                save_m2_state()

                            runtime.save_snapshot = collection_checkpoint
                            runtime.graph_snapshot = envelope.get("collection_snapshot")

                            collection_interrupted = bool(envelope.get("collection_in_flight"))

                            m1_report = envelope.get("collection_report")
                            m1_report_recomputed = False
                            if (
                                supplemental_input is not None
                                and m1_report is not None
                                and bool(m1_report.get("missing_fields"))
                                and envelope.get("research_snapshot") is None
                            ):
                                from .agents import run_supplement_graph
                                m1_report = await run_supplement_graph(
                                    m1_report, supplemental_input, runtime,
                                    received_at=received_at.isoformat() if received_at else None,
                                )
                                m1_report_recomputed = True
                                envelope["collection_report"] = m1_report
                                collection_checkpoint(runtime.graph_snapshot or {})
                                save_m2_state(updated_report=m1_report, updated_raw_file=raw_file)
                            elif m1_report is None and not collection_interrupted:
                                collection_hop = 0

                                def reserve_collection_hop():
                                    nonlocal collection_hop
                                    collection_hop += 1
                                    if not reserve_call(settings.external_timeout_seconds, 1):
                                        return False
                                    envelope["collection_in_flight"] = {
                                        "claim_token": claim_token,
                                        "hop": collection_hop,
                                    }
                                    save_m2_state()
                                    return True

                                if engine.dialect.name == "postgresql":
                                    conninfo = make_url(settings.database_url).set(
                                        drivername="postgresql"
                                    ).render_as_string(hide_password=False)
                                    async with AsyncPostgresSaver.from_conn_string(conninfo) as checkpointer:
                                        page = await collect_page(
                                            url, timeout=settings.external_timeout_seconds,
                                            reserve_request=reserve_collection_hop,
                                        )
                                        raw_file = store_html(
                                            settings.raw_storage_dir, analysis_id, claim_token, page.html
                                        )
                                        m1_report = await run_collection_graph(
                                            page, product_name, runtime, checkpointer=checkpointer,
                                            thread_id=f"{analysis_id}:{claim_token}",
                                        )
                                else:
                                    page = await collect_page(
                                        url, timeout=settings.external_timeout_seconds,
                                        reserve_request=reserve_collection_hop,
                                    )
                                    raw_file = store_html(
                                        settings.raw_storage_dir, analysis_id, claim_token, page.html
                                    )
                                    m1_report = await run_collection_graph(page, product_name, runtime)
                                envelope["collection_report"] = m1_report
                                envelope.pop("collection_in_flight", None)
                                save_m2_state(updated_report=m1_report, updated_raw_file=raw_file)

                            if collection_interrupted:
                                report = interrupted_collection_report(m1_report)
                                envelope.pop("collection_in_flight", None)
                                save_m2_state(updated_report=report)
                                status = "completed"
                            elif m1_report.get("missing_fields"):
                                report = dict(m1_report)
                                report["scope"] = "collection_only"
                                report["research"] = {"status": "not_started", "reason": "needs_input"}
                                status = "needs_input"
                                error_code = "insufficient_information"
                                message = (
                                    "추가 정보로 확인 가능한 범위를 정리했습니다. 남은 항목은 확인되지 않았습니다."
                                    if supplemental_input is not None
                                    else "제품 식별에 필요한 정보를 한 번에 확인해 주세요."
                                )
                            else:
                                with sessions() as db:
                                    current = get_analysis(db, analysis_id)
                                    runtime.initial_tool_calls = current.tool_calls_reserved
                                runtime.research_started = bool(
                                    envelope.get("collection_report") is not None
                                    and envelope.get("research_snapshot") is None
                                    and snapshot is not None
                                    and not m1_report_recomputed
                                )

                                def research_checkpoint(value):
                                    envelope["research_snapshot"] = value
                                    save_m2_state(updated_report=value.get("report"))

                                runtime.save_snapshot = research_checkpoint
                                runtime.graph_snapshot = envelope.get("research_snapshot")
                                research_result = await run_research_graph(
                                    m1_report, runtime, checkpoint=research_checkpoint,
                                    snapshot=envelope.get("research_snapshot"),
                                    remaining_seconds=max(0.1, window - (time.monotonic() - worker_started)),
                                )
                                report = research_result["report"]
                                envelope["research_snapshot"] = research_result["snapshot"]
                                save_m2_state(updated_report=report)
                                status = "completed"
                                if research_result.get("yielded"):
                                    with sessions() as db:
                                        current = get_analysis(db, analysis_id)
                                        next_window = min(settings.attempt_timeout_seconds, settings.analysis_timeout_seconds)
                                        can_yield = (
                                            current.attempt_count < 3
                                            and current.active_seconds_reserved + next_window <= settings.analysis_timeout_seconds
                                        )
                                        if can_yield:
                                            yielded_to_queue = yield_analysis(
                                                db, analysis_id, claim_token=claim_token,
                                                snapshot=envelope, report=report,
                                            )
                                            db.commit()
                                    if not can_yield:
                                        yielded_to_queue = False
                    elif supplemental_input is not None:
                        from .agents import run_supplement_graph

                        report = await run_supplement_graph(
                            stored_report or {}, supplemental_input, runtime,
                            received_at=received_at.isoformat() if received_at else None,
                        )
                    elif engine.dialect.name == "postgresql":
                        conninfo = (
                            make_url(settings.database_url)
                            .set(drivername="postgresql")
                            .render_as_string(hide_password=False)
                        )
                        async with AsyncPostgresSaver.from_conn_string(conninfo) as checkpointer:
                            if not reserve_call(settings.external_timeout_seconds, 1):
                                raise CollectionError("budget_exhausted", "도구 호출 한도에 도달했습니다.")
                            page = await collect_page(url, timeout=settings.external_timeout_seconds)
                            raw_file = store_html(settings.raw_storage_dir, analysis_id, claim_token, page.html)
                            report = await run_collection_graph(
                                page, product_name, runtime,
                                checkpointer=checkpointer,
                                thread_id=f"{analysis_id}:{claim_token}",
                            )
                    else:
                        # SQLite is confined to isolated automated tests.
                        if not reserve_call(settings.external_timeout_seconds, 1):
                            raise CollectionError("budget_exhausted", "도구 호출 한도에 도달했습니다.")
                        page = await collect_page(url, timeout=settings.external_timeout_seconds)
                        raw_file = store_html(settings.raw_storage_dir, analysis_id, claim_token, page.html)
                        report = await run_collection_graph(page, product_name, runtime)
                    status = "needs_input" if report.get("missing_fields") else "completed"
                    if status == "needs_input":
                        error_code = "insufficient_information"
                        message = (
                            "추가 정보로 확인 가능한 범위를 정리했습니다. 남은 항목은 확인되지 않았습니다."
                            if supplemental_input is not None
                            else "제품 식별에 필요한 정보를 한 번에 확인해 주세요."
                        )
            except CollectionError as exc:
                error_code, message = exc.code, exc.message
            except TimeoutError:
                error_code, message = (
                    "active_time_limit",
                    "이번 실행의 활성 시간 한도에 도달했습니다.",
                )
            except Exception:
                error_code, message = "processing_failed", "수집 보고서를 처리하지 못했습니다."
            if (
                mode == "evidence_review"
                and isinstance(envelope, dict)
                and envelope.get("collection_in_flight")
            ):
                report = interrupted_collection_report(envelope.get("collection_report"))

        if yielded_to_queue:
            return
        with sessions() as session:
            final_report = report
            if supplemental_input is not None and final_report is None:
                final_report = stored_report
            if mode == "evidence_review" and final_report is None:
                latest = get_analysis(session, analysis_id)
                final_report = latest.report if latest is not None else None
            finish_analysis(
                session,
                analysis_id,
                claim_token=claim_token,
                status=status,
                report=final_report,
                error_code=error_code,
                message=message,
                raw_file=raw_file,
            )
            session.commit()
    finally:
        engine.dispose()


@celery_app.task(name="supplement_advisor.process_analysis")
def process_analysis(analysis_id: str) -> None:
    asyncio.run(execute_analysis(analysis_id, get_settings()))


@celery_app.task(name="supplement_advisor.recover_pending")
def recover_pending() -> int:
    engine = make_engine(get_settings().database_url)
    try:
        with session_factory(engine)() as session:
            pending = list_dispatchable(session)
        published = 0
        for analysis_id in pending:
            try:
                process_analysis.delay(analysis_id)
                published += 1
            except Exception:
                break  # The next beat scan retries the persisted rows.
        return published
    finally:
        engine.dispose()
