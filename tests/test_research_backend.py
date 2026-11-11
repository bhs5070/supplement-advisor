"""M2-A durable mode, API, and worker integration tests."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from supplement_advisor.collection import CollectedPage
from supplement_advisor.config import Settings
from supplement_advisor.database import make_engine, session_factory
from supplement_advisor.main import create_app
from supplement_advisor.models import Analysis, Base
from supplement_advisor.repository import create_analysis, get_analysis, yield_analysis
from supplement_advisor.tasks import execute_analysis

PROJECT = Path(__file__).resolve().parents[1]


def test_analysis_mode_defaults_to_collection_and_can_be_set(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'mode.db'}")
    Base.metadata.create_all(engine)
    try:
        with session_factory(engine).begin() as session:
            collection = create_analysis(
                session, url="https://example.com", product_name=None,
                token_hash=hashlib.sha256(b"collection").hexdigest(),
            )
            evidence = create_analysis(
                session, url="https://example.com", product_name=None,
                token_hash=hashlib.sha256(b"evidence").hexdigest(), mode="evidence_review",
            )
            assert getattr(collection, "mode", None) == "collection"
            assert evidence.mode == "evidence_review"
    finally:
        engine.dispose()


def test_migration_preserves_existing_rows_as_collection(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'migrate-existing.db'}")
    config = Config(str(PROJECT / "alembic.ini"))
    identity = "00000000-0000-0000-0000-000000000003"
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002_m1_supplement")
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(text(
            "INSERT INTO analyses (id, token_hash, url, status, created_at, updated_at, attempt_count) "
            "VALUES (:id, :token, :url, 'queued', :created, :updated, 0)"
        ), {"id": identity, "token": "a" * 64, "url": "https://example.com",
            "created": now, "updated": now})
        command.upgrade(config, "head")
        assert connection.execute(
            text("SELECT mode FROM analyses WHERE id = :id"), {"id": identity}
        ).scalar_one() == "collection"
    engine.dispose()


def test_yield_is_fenced_and_preserves_all_reservations(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'yield.db'}")
    Base.metadata.create_all(engine)
    try:
        with session_factory(engine).begin() as session:
            row = create_analysis(
                session, url="https://example.com", product_name=None,
                token_hash=hashlib.sha256(b"yield").hexdigest(), mode="evidence_review",
            )
            identity = row.id
        with session_factory(engine).begin() as session:
            from supplement_advisor.repository import claim_analysis, reserve_budget

            row = claim_analysis(session, identity)
            token = row.claim_token
            assert reserve_budget(session, identity, claim_token=token, seconds=60, tool_calls=3)
            row.raw_file = "private/page.html"
            row.supplemental_input = {"manufacturer": "Example"}
            row.attempt_count = 2
        snapshot = {"phase": "roles"}
        report = {"scope": "evidence_review", "score": None, "verdict": "hold"}
        with session_factory(engine).begin() as session:
            assert yield_analysis(
                session, identity, claim_token=token, snapshot=snapshot, report=report
            )
        with session_factory(engine)() as session:
            row = get_analysis(session, identity)
            assert row.status == "queued" and row.claim_token is None
            assert row.graph_snapshot == snapshot and row.report == report
            assert (row.attempt_count, row.active_seconds_reserved, row.tool_calls_reserved) == (2, 60, 3)
            assert row.raw_file == "private/page.html"
            assert row.supplemental_input == {"manufacturer": "Example"}
    finally:
        engine.dispose()


def test_yield_rejects_expired_lease(tmp_path):
    from datetime import timedelta

    from sqlalchemy import update

    from supplement_advisor.models import utc_now
    from supplement_advisor.repository import claim_analysis

    engine = make_engine(f"sqlite:///{tmp_path / 'expired-yield.db'}")
    Base.metadata.create_all(engine)
    try:
        with session_factory(engine).begin() as db:
            row = create_analysis(
                db, url="https://example.com", product_name=None,
                token_hash=hashlib.sha256(b"expired-yield").hexdigest(),
            )
            identity = row.id
        with session_factory(engine).begin() as db:
            row = claim_analysis(db, identity)
            claim_token = row.claim_token
            db.execute(update(Analysis).where(Analysis.id == identity).values(
                lease_expires_at=utc_now() - timedelta(seconds=1),
            ))
        with session_factory(engine).begin() as db:
            assert not yield_analysis(
                db, identity, claim_token=claim_token,
                snapshot={"phase": "roles"}, report={"scope": "evidence_review"},
            )
    finally:
        engine.dispose()


def test_supplement_acceptance_preserves_evidence_mode_snapshot_and_single_use(tmp_path):
    from supplement_advisor.repository import accept_supplement

    engine = make_engine(f"sqlite:///{tmp_path / 'supplement-mode.db'}")
    Base.metadata.create_all(engine)
    try:
        with session_factory(engine).begin() as session:
            row = create_analysis(
                session, url="https://example.com", product_name=None,
                token_hash=hashlib.sha256(b"supplement-mode").hexdigest(), mode="evidence_review",
            )
            row.status = "needs_input"
            row.graph_snapshot = {"version": 1, "mode": "evidence_review"}
            identity, token_hash = row.id, row.token_hash
        with session_factory(engine).begin() as session:
            assert accept_supplement(session, identity, token_hash, {"manufacturer": "Example"})
        with session_factory(engine).begin() as session:
            row = get_analysis(session, identity)
            assert row.mode == "evidence_review" and row.status == "queued"
            assert row.graph_snapshot == {"version": 1, "mode": "evidence_review"}
            assert not accept_supplement(session, identity, token_hash, {"manufacturer": "Again"})
    finally:
        engine.dispose()


def test_evidence_supplement_keeps_mode_and_marks_second_attempt_unavailable(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'api-supp.db'}")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    try:
        accepted = client.post("/api/analyses", json={
            "url": "https://example.com", "mode": "evidence_review",
        }).json()
        with session_factory(engine).begin() as session:
            row = get_analysis(session, accepted["id"])
            row.status = "needs_input"
            row.report = {"scope": "collection_only", "missing_fields": ["manufacturer"]}
            row.graph_snapshot = {
                "version": 1, "mode": "evidence_review", "collection_snapshot": None,
                "collection_report": row.report, "research_snapshot": None,
            }
        path = f"/api/analyses/{accepted['id']}/supplement"
        headers = {"X-Analysis-Token": accepted["access_token"]}
        payload = {"manufacturer": "Example"}
        assert client.post(path, json=payload, headers=headers).status_code == 202
        result = client.get(f"/api/analyses/{accepted['id']}", headers=headers).json()
        assert result["mode"] == "evidence_review"
        assert result["supplemental_input_used"] and not result["can_supplement"]
        assert client.post(path, json={"manufacturer": "Again"}, headers=headers).status_code == 409
    finally:
        client.close()
        engine.dispose()


def test_api_accepts_and_returns_mode_and_keeps_token_404(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'api.db'}")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    try:
        accepted = client.post("/api/analyses", json={
            "url": "https://example.com", "mode": "evidence_review",
        })
        assert accepted.status_code == 202
        data = accepted.json()
        assert data["mode"] == "evidence_review"
        result = client.get(f"/api/analyses/{data['id']}", headers={
            "X-Analysis-Token": data["access_token"],
        })
        assert result.json()["mode"] == "evidence_review"
        assert client.get(f"/api/analyses/{data['id']}").status_code == 404
        assert client.post("/api/analyses", json={
            "url": "https://example.com", "mode": "unknown",
        }).status_code == 422
    finally:
        client.close()
        engine.dispose()


async def test_evidence_worker_reserves_each_collection_request_and_saves_m1_before_research(
    tmp_path, monkeypatch
):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        raw_storage_dir=tmp_path / "private", openai_api_key="test-key",
        tavily_api_key="test-tavily", food_safety_api_key=None,
    )
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    accepted = client.post("/api/analyses", json={
        "url": "https://example.com", "mode": "evidence_review",
    }).json()
    observed = {}

    async def collect(_url, *, timeout, reserve_request=None):
        assert timeout == settings.external_timeout_seconds
        assert reserve_request is not None
        assert reserve_request() and reserve_request()
        return CollectedPage("https://example.com", "product", "text", "<html>raw</html>", [])

    async def collect_graph(_page, _name, runtime, **_kwargs):
        observed["m1_snapshot"] = runtime.graph_snapshot
        observed["m1_report"] = {"scope": "collection_only", "missing_fields": [], "product": {}, "report": {}}
        return observed["m1_report"]

    async def research(collection, runtime, **kwargs):
        observed["calls"] = runtime.initial_tool_calls
        observed["keys"] = (runtime.model_timeout_seconds, runtime.tavily_api_key)
        observed["prior"] = kwargs.get("snapshot")
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            observed["saved_before_research"] = row.report == collection and bool(row.raw_file)
        return {
            "report": {"scope": "evidence_review", "score": None, "verdict": "hold",
                       "research": {"status": "completed"}},
            "snapshot": {"version": 1, "phase": "report"}, "yielded": False,
        }

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", collect)
    monkeypatch.setattr("supplement_advisor.tasks.run_collection_graph", collect_graph)
    monkeypatch.setattr("supplement_advisor.agents.run_research_graph", research)
    try:
        await execute_analysis(accepted["id"], settings)
        with session_factory(engine)() as db:
            debug_row = get_analysis(db, accepted["id"])
            assert debug_row.status == "completed", (debug_row.status, debug_row.error_code, debug_row.message)
        assert observed["calls"] == 2
        assert observed["keys"] == (settings.model_timeout_seconds, settings.tavily_api_key)
        assert observed["prior"] is None and observed["saved_before_research"]
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            assert row.status == "completed" and row.mode == "evidence_review"
            assert row.tool_calls_reserved == 2
            assert row.graph_snapshot["collection_report"] == observed["m1_report"]
            assert row.graph_snapshot["research_snapshot"]["phase"] == "report"
    finally:
        client.close()
        engine.dispose()


async def test_graceful_research_yield_queues_and_resumes_without_recollecting(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'resume.db'}",
        raw_storage_dir=tmp_path / "private", openai_api_key="test-key", tavily_api_key="test-key",
    )
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    accepted = client.post("/api/analyses", json={
        "url": "https://example.com", "mode": "evidence_review",
    }).json()
    collections, calls = [], []

    async def collect(_url, *, reserve_request=None, **_kwargs):
        collections.append(True)
        assert reserve_request()
        return CollectedPage("https://example.com", "product", "text", "<html/>", [])

    async def collect_graph(*_args, **_kwargs):
        return {"scope": "collection_only", "missing_fields": [], "product": {}, "report": {}}

    async def research(collection, _runtime, *, snapshot=None, **_kwargs):
        calls.append(snapshot)
        next_snapshot = {"phase": "roles"} if snapshot is None else {"phase": "report"}
        return {
            "report": {"scope": "evidence_review", "score": None, "verdict": "hold",
                       "research": {"status": "partial"}},
            "snapshot": next_snapshot, "yielded": snapshot is None,
        }

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", collect)
    monkeypatch.setattr("supplement_advisor.tasks.run_collection_graph", collect_graph)
    monkeypatch.setattr("supplement_advisor.agents.run_research_graph", research)
    try:
        await execute_analysis(accepted["id"], settings)
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            assert row.status == "queued" and row.attempt_count == 1, (row.status, row.error_code, row.report)
            assert row.graph_snapshot["research_snapshot"] == {"phase": "roles"}
            assert row.active_seconds_reserved == 60 and row.tool_calls_reserved == 1
        await execute_analysis(accepted["id"], settings)
        assert len(collections) == 1 and calls == [None, {"phase": "roles"}]
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            assert row.status == "completed" and row.attempt_count == 2
            assert row.active_seconds_reserved == 120 and row.tool_calls_reserved == 1
    finally:
        client.close()
        engine.dispose()


async def test_first_research_after_supplement_is_not_misclassified_as_resume(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'first-after-supp.db'}")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    accepted = client.post("/api/analyses", json={
        "url": "https://example.com", "mode": "evidence_review",
    }).json()
    old_report = {"scope": "collection_only", "missing_fields": ["manufacturer"]}
    envelope = {"version": 1, "mode": "evidence_review", "collection_snapshot": None,
                "collection_report": old_report, "research_snapshot": None}
    with session_factory(engine).begin() as db:
        row = get_analysis(db, accepted["id"])
        row.supplemental_input = {"manufacturer": "Example"}
        row.supplemental_received_at = datetime.now(timezone.utc)
        row.report = old_report
        row.graph_snapshot = envelope
    seen = {}

    async def supplement(_old_report, _payload, _runtime, **_kwargs):
        return {"scope": "collection_only", "missing_fields": [], "product": {}}

    async def research(_collection, runtime, **kwargs):
        seen["research_started"] = runtime.research_started
        seen["snapshot"] = kwargs.get("snapshot")
        return {"report": {"scope": "evidence_review", "score": None, "verdict": "hold"},
                "snapshot": {"phase": "report"}, "yielded": False}

    monkeypatch.setattr("supplement_advisor.agents.run_supplement_graph", supplement)
    monkeypatch.setattr("supplement_advisor.agents.run_research_graph", research)
    monkeypatch.setattr("supplement_advisor.tasks.collect_page", lambda *_a, **_k: None)
    try:
        await execute_analysis(accepted["id"], settings)
        assert seen == {"research_started": False, "snapshot": None}
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            assert row.status == "completed"
    finally:
        client.close()
        engine.dispose()


async def test_yield_on_third_attempt_finishes_partial_without_requeue(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'last-yield.db'}")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    accepted = client.post("/api/analyses", json={
        "url": "https://example.com", "mode": "evidence_review",
    }).json()
    collection = {"scope": "collection_only", "missing_fields": []}
    with session_factory(engine).begin() as db:
        row = get_analysis(db, accepted["id"])
        row.report = collection
        row.graph_snapshot = {"version": 1, "mode": "evidence_review",
                              "collection_snapshot": None, "collection_report": collection,
                              "research_snapshot": {"phase": "roles"}}
        row.attempt_count = 2
        row.active_seconds_reserved = 120

    async def must_not_collect(*_args, **_kwargs):
        raise AssertionError("completed M1 state must be reused")

    async def yield_result(*_args, **_kwargs):
        return {"report": {"scope": "evidence_review", "score": None, "verdict": "hold",
                           "research": {"status": "partial"}},
                "snapshot": {"phase": "roles"}, "yielded": True}

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", must_not_collect)
    monkeypatch.setattr("supplement_advisor.agents.run_research_graph", yield_result)
    try:
        await execute_analysis(accepted["id"], settings)
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            assert row.status == "completed" and row.attempt_count == 3
            assert row.active_seconds_reserved == 180
            assert row.report["research"]["status"] == "partial"
    finally:
        client.close()
        engine.dispose()


async def test_completed_supplement_is_not_replayed_when_research_snapshot_exists(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'supp-resume.db'}")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    accepted = client.post("/api/analyses", json={
        "url": "https://example.com", "mode": "evidence_review",
    }).json()
    m1 = {"scope": "collection_only", "missing_fields": [], "product": {"name": "saved"}}
    research_snapshot = {"version": 1, "phase": "roles"}
    envelope = {"version": 1, "mode": "evidence_review", "collection_snapshot": {"version": 10},
                "collection_report": m1, "research_snapshot": research_snapshot}
    with session_factory(engine).begin() as db:
        row = get_analysis(db, accepted["id"])
        row.supplemental_input = {"manufacturer": "Example"}
        row.supplemental_received_at = datetime.now(timezone.utc)
        row.report = {"scope": "evidence_review", "collection_report": m1}
        row.graph_snapshot = envelope
    supplements, resumed = [], []

    async def unexpected_supplement(*_args, **_kwargs):
        supplements.append(True)
        raise AssertionError("completed supplement must not be replayed")

    async def research(_collection, _runtime, *, snapshot=None, **_kwargs):
        resumed.append(snapshot)
        return {"report": {"scope": "evidence_review", "score": None, "verdict": "hold"},
                "snapshot": snapshot, "yielded": False}

    monkeypatch.setattr("supplement_advisor.agents.run_supplement_graph", unexpected_supplement)
    monkeypatch.setattr("supplement_advisor.agents.run_research_graph", research)
    try:
        await execute_analysis(accepted["id"], settings)
        assert supplements == [] and resumed == [research_snapshot]
    finally:
        client.close()
        engine.dispose()


async def test_invalid_m2_envelope_preserves_saved_collection_fields(tmp_path, monkeypatch):
    from supplement_advisor.agents.research_types import ResearchResult

    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'invalid-envelope.db'}")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    accepted = client.post("/api/analyses", json={
        "url": "https://example.com", "mode": "evidence_review",
    }).json()
    m1 = {"scope": "collection_only", "missing_fields": [], "product": {"name": "keep-me"}}
    with session_factory(engine).begin() as db:
        row = get_analysis(db, accepted["id"])
        row.report = m1
        row.graph_snapshot = {"broken": True}
        row.tool_calls_reserved = 7
    try:
        await execute_analysis(accepted["id"], settings)
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            assert row.report["collection_report"]["product"]["name"] == "keep-me"
            result = ResearchResult.model_validate(row.report["research"])
            roles = {role.role: role for role in result.roles}
            assert set(roles) == {"composition", "claims", "personal_fit", "safety", "official_quality"}
            assert roles["personal_fit"].status == "not_applicable"
            assert result.termination_reason == "snapshot_invalid"
            assert result.sources == []
            assert result.usage["total"] == 7
            assert result.usage["by_role"] is None
            assert result.usage["attribution"] == "unavailable"
    finally:
        client.close()
        engine.dispose()


async def test_research_exception_preserves_fenced_m1_report_and_raw_file(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'exception-preserve.db'}",
        raw_storage_dir=tmp_path / "private",
    )
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    async def validate(_url):
        return None
    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    accepted = client.post("/api/analyses", json={
        "url": "https://example.com", "mode": "evidence_review",
    }).json()
    m1 = {"scope": "collection_only", "missing_fields": [], "product": {"name": "kept"}}

    async def collect(_url, *, reserve_request=None, **_kwargs):
        assert reserve_request()
        return CollectedPage("https://example.com", "product", "text", "<html/>", [])

    async def collect_graph(*_args, **_kwargs):
        return m1

    async def fail_research(*_args, **_kwargs):
        raise RuntimeError("synthetic research failure")

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", collect)
    monkeypatch.setattr("supplement_advisor.tasks.run_collection_graph", collect_graph)
    monkeypatch.setattr("supplement_advisor.agents.run_research_graph", fail_research)
    try:
        await execute_analysis(accepted["id"], settings)
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            assert row.status == "failed" and row.error_code == "processing_failed"
            assert row.report["product"]["name"] == "kept"
            assert row.raw_file is not None
    finally:
        client.close()
        engine.dispose()


async def test_interrupted_m2_collection_is_durable_and_never_refetched(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'interrupted-m2.db'}",
        raw_storage_dir=tmp_path / "private",
    )
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)

    async def validate(_url):
        return None

    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _id: None))
    accepted = client.post("/api/analyses", json={
        "url": "https://example.com", "mode": "evidence_review",
    }).json()
    attempts = []

    async def crash_after_durable_reservation(_url, *, timeout, reserve_request=None):
        attempts.append("fetch")
        assert reserve_request()
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", crash_after_durable_reservation)
    try:
        await execute_analysis(accepted["id"], settings)
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            marker = row.graph_snapshot.get("collection_in_flight")
            assert marker and marker["claim_token"]
            reserved = row.tool_calls_reserved
            assert reserved > 0
            assert row.report["research"]["usage"]["total"] == reserved
        # Model a hard worker exit: the lease expires and the durable queue scan reclaims it.
        with session_factory(engine).begin() as db:
            row = get_analysis(db, accepted["id"])
            row.status = "queued"
            row.claim_token = None
            row.lease_expires_at = None

        async def must_not_fetch(*_args, **_kwargs):
            attempts.append("refetch")
            raise AssertionError("interrupted M2 request must not be retried")

        monkeypatch.setattr("supplement_advisor.tasks.collect_page", must_not_fetch)
        await execute_analysis(accepted["id"], settings)
        with session_factory(engine)() as db:
            row = get_analysis(db, accepted["id"])
            assert row.status == "completed"
            assert row.report["research"]["termination_reason"] == "unknown_interrupted"
            assert row.report["research"]["status"] == "partial"
            assert row.report["research"]["usage"]["total"] == row.tool_calls_reserved
            assert not row.graph_snapshot.get("collection_in_flight")
            assert attempts == ["fetch"]
    finally:
        client.close()
        engine.dispose()
