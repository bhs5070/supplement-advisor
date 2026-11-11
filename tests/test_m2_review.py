"""Independent connection checks for M2 persistence and the opt-in verifier."""

import hashlib
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect, select

from supplement_advisor.agents import run_research_graph
from supplement_advisor.agents.research_types import (
    ResearchSource,
    SupervisorDecision,
    normalize_sources,
)
from supplement_advisor.database import make_engine, session_factory
from supplement_advisor.models import Analysis
from supplement_advisor.repository import (
    claim_analysis,
    create_analysis,
    get_analysis,
    reserve_budget,
    save_snapshot,
    yield_analysis,
)

PROJECT = Path(__file__).resolve().parents[1]
_live_spec = importlib.util.spec_from_file_location(
    "verify_research_live", PROJECT / "scripts" / "verify_research_live.py"
)
verify_research_live = importlib.util.module_from_spec(_live_spec)
_live_spec.loader.exec_module(verify_research_live)
_local_base = verify_research_live._local_base
verify = verify_research_live.verify


def _migrate(engine, revision="head", *, downgrade=False):
    config = Config(str(PROJECT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(config, revision)


@pytest.fixture(params=["sqlite", "postgresql"])
def isolated_db(request, tmp_path):
    cleanup = None
    if request.param == "sqlite":
        engine = make_engine(f"sqlite:///{tmp_path / 'm2-review.sqlite'}")
    else:
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL is not configured; real PostgreSQL unverified")
        cleanup = make_engine(url)
        if cleanup.dialect.name != "postgresql":
            cleanup.dispose()
            pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
        schema = "test_m2_review_" + uuid4().hex
        with cleanup.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = make_engine(url)

        @event.listens_for(engine, "connect")
        def set_schema(dbapi_connection, _record):
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f'SET SESSION search_path TO "{schema}"')
            dbapi_connection.commit()

    try:
        _migrate(engine)
        yield engine
    finally:
        engine.dispose()
        if cleanup is not None:
            with cleanup.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            cleanup.dispose()


def _new(sessions):
    with sessions.begin() as session:
        row = create_analysis(
            session,
            url="https://example.com",
            product_name=None,
            token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
            mode="evidence_review",
        )
        return row.id


def test_yield_is_fenced_and_keeps_budget_and_snapshot(isolated_db):
    sessions = session_factory(isolated_db)
    identity = _new(sessions)
    with sessions.begin() as session:
        first = claim_analysis(session, identity)
        assert first is not None
        stale = first.claim_token
        assert reserve_budget(session, identity, claim_token=stale, seconds=60, tool_calls=2)
    snapshot = {"mode": "evidence_review", "research_snapshot": {"phase": "supervisor"}}
    report = {"scope": "evidence_review", "score": None, "verdict": "hold"}
    with sessions.begin() as session:
        assert yield_analysis(
            session, identity, claim_token=stale, snapshot=snapshot, report=report
        )
    with sessions() as session:
        queued = get_analysis(session, identity)
        assert queued.status == "queued" and queued.claim_token is None
        assert queued.active_seconds_reserved == 60 and queued.tool_calls_reserved == 2
        assert queued.graph_snapshot == snapshot and queued.report == report
    with sessions.begin() as session:
        new = claim_analysis(session, identity)
        assert new is not None and new.claim_token != stale
    with sessions.begin() as session:
        assert not yield_analysis(session, identity, claim_token=stale, snapshot={}, report={})
        assert not save_snapshot(session, identity, claim_token=stale, snapshot={})
    with sessions() as session:
        assert get_analysis(session, identity).graph_snapshot == snapshot


def test_only_one_competing_yield_succeeds(isolated_db):
    sessions = session_factory(isolated_db)
    identity = _new(sessions)
    with sessions.begin() as session:
        claim = claim_analysis(session, identity)
        claim_token = claim.claim_token
    barrier = Barrier(2)

    def try_yield(index):
        barrier.wait()
        with sessions.begin() as session:
            return yield_analysis(
                session,
                identity,
                claim_token=claim_token,
                snapshot={"winner": index},
                report={"sequence": index},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(try_yield, range(2)))
    assert sum(results) == 1
    with sessions() as session:
        row = get_analysis(session, identity)
        assert row.status == "queued" and row.graph_snapshot["winner"] in (0, 1)


@pytest.mark.asyncio
async def test_graph_database_callbacks_keep_exact_reservations_and_stop_on_save_failure(
    isolated_db, monkeypatch
):
    sessions = session_factory(isolated_db)
    identity = _new(sessions)
    with sessions.begin() as session:
        claimed = claim_analysis(session, identity)
        token = claimed.claim_token
    parsed_calls = []

    class Responses:
        async def parse(self, **kwargs):
            parsed_calls.append(kwargs)
            return SimpleNamespace(
                output_parsed=SupervisorDecision(
                    action="finish", reason="No further specialist lookup is needed"
                ),
                status="completed",
            )

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.responses = Responses()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", FakeClient)

    def reserve(**kwargs):
        with sessions.begin() as session:
            return reserve_budget(
                session, identity, claim_token=token, seconds=0, tool_calls=kwargs["tool_calls"]
            )

    def checkpoint(snapshot):
        with sessions.begin() as session:
            assert save_snapshot(session, identity, claim_token=token, snapshot=snapshot)

    settings = SimpleNamespace(
        openai_api_key="mock-only",
        openai_model="mock",
        model_timeout_seconds=1,
        external_timeout_seconds=1,
        analysis_timeout_seconds=30,
        max_tool_calls=20,
        reserve_budget=reserve,
        save_snapshot=checkpoint,
    )
    collection = {"product": {"name": "Fixture"}, "scope": "collection_only"}
    result = await run_research_graph(collection, settings, checkpoint=checkpoint)
    with sessions() as session:
        stored = get_analysis(session, identity)
        saved_total = stored.tool_calls_reserved
        saved_snapshot = stored.graph_snapshot
    assert len(parsed_calls) == 1
    assert saved_total == result["snapshot"]["counters"]["total"] == 1
    assert result["report"]["research"]["usage"]["total"] == saved_total
    assert saved_snapshot["counters"] == result["snapshot"]["counters"]

    # The next analysis proves a DB checkpoint rejection prevents a model request.
    second = _new(sessions)
    with sessions.begin() as session:
        second_claim = claim_analysis(session, second)

    def reject_checkpoint(_snapshot):
        with sessions.begin() as session:
            return save_snapshot(session, second, claim_token="stale-fence", snapshot={})

    def reserve_second(**kwargs):
        with sessions.begin() as session:
            return reserve_budget(
                session,
                second,
                claim_token=second_claim.claim_token,
                seconds=0,
                tool_calls=kwargs["tool_calls"],
            )

    settings_second = SimpleNamespace(**vars(settings))
    settings_second.reserve_budget = reserve_second
    before = len(parsed_calls)
    failed = await run_research_graph(collection, settings_second, checkpoint=reject_checkpoint)
    assert len(parsed_calls) == before
    assert failed["report"]["research"]["termination_reason"] == "lease_lost"
    with sessions() as session:
        failed_row = get_analysis(session, second)
        assert failed_row.tool_calls_reserved == 1
    assert failed["report"]["research"]["usage"]["total"] == failed_row.tool_calls_reserved


def test_0003_defaults_existing_0002_rows_to_collection(isolated_db):
    if isolated_db.dialect.name != "postgresql":
        pytest.skip("existing-row migration assertion requires PostgreSQL")
    _migrate(isolated_db, "0002_m1_supplement", downgrade=True)
    identity = str(uuid4())
    with isolated_db.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO analyses (id, token_hash, url, status, created_at, updated_at, "
            "attempt_count, active_seconds_reserved, tool_calls_reserved, report) "
            'VALUES (%s, %s, %s, %s, now(), now(), 0, 0, 0, \'{"scope": "collection_only", "score": null}\'::json)',
            (identity, "a" * 64, "https://example.com", "queued"),
        )
    _migrate(isolated_db)
    with isolated_db.connect() as connection:
        assert "mode" in {column["name"] for column in inspect(connection).get_columns("analyses")}
        row = connection.execute(
            select(Analysis.mode, Analysis.report).where(Analysis.id == identity)
        ).one()
        assert row.mode == "collection"
        assert row.report == {"scope": "collection_only", "score": None}


def test_source_registry_promotion_replaces_discovery_record():
    discovery = ResearchSource(
        id="source-1",
        kind="discovery",
        title="Found title",
        url="https://example.org/paper",
        retrieved_at="2026-11-11T00:00:00Z",
        provider="tavily",
        pmid="12345",
        access_scope="discovery",
        excerpt="",
        text="",
    )
    official_document = discovery.model_copy(
        update={
            "kind": "official",
            "provider": "registry",
            "access_scope": "document",
            "excerpt": "Full text evidence",
            "text": "Full text evidence with details",
        }
    )
    merged = normalize_sources([discovery, official_document])
    assert len(merged) == 1
    assert merged[0].id == "source-1" and merged[0].kind == "official"
    assert merged[0].access_scope == "document" and "details" in merged[0].text


def test_source_registry_deduplicates_promoted_discovery_without_identifier():
    discovery = ResearchSource(
        id="same-source",
        kind="discovery",
        title="Found title",
        url="https://example.org/paper",
        retrieved_at="2026-11-11T00:00:00Z",
        provider="tavily",
        access_scope="discovery",
        excerpt="",
        text="",
    )
    document = discovery.model_copy(
        update={
            "kind": "official",
            "provider": "registry",
            "access_scope": "document",
            "excerpt": "Retrieved evidence",
            "text": "Retrieved evidence in full",
        }
    )
    merged = normalize_sources([discovery, document])
    assert len(merged) == 1
    assert merged[0].kind == "official" and merged[0].access_scope == "document"


def test_source_registry_full_text_promotion_replaces_abstract():
    abstract = ResearchSource(
        id="paper-2",
        kind="research",
        title="Paper",
        url="https://example.org/abstract",
        retrieved_at="2026-11-11T00:00:00Z",
        provider="pubmed",
        pmid="67890",
        access_scope="abstract",
        excerpt="Abstract only",
        text="Abstract only content",
    )
    full_text = abstract.model_copy(
        update={
            "url": "https://example.org/full-text",
            "access_scope": "document",
            "excerpt": "Full text includes methods",
            "text": "Full text includes methods and results",
        }
    )
    merged = normalize_sources([abstract, full_text])
    assert len(merged) == 1
    assert merged[0].access_scope == "document"
    assert "methods and results" in merged[0].text


@pytest.mark.parametrize(
    "url", ["https://example.com", "http://192.168.1.1", "http://localhost.evil"]
)
def test_live_verifier_rejects_non_loopback(url):
    with pytest.raises(ValueError):
        _local_base(url)


def _research_report(
    *, research_sources=None, m1_sources=None, collection_sources=None, roles=None, decisions=None
):
    role_rows = roles or [
        {
            "role": role,
            "status": "not_applicable" if role == "personal_fit" else "insufficient_evidence",
        }
        for role in ("composition", "claims", "personal_fit", "safety", "official_quality")
    ]
    return {
        "scope": "evidence_review",
        "collection_report": {"scope": "collection_only", "sources": collection_sources or []},
        "score": None,
        "verdict": "hold",
        "sources": m1_sources or [],
        "research": {
            "status": "partial",
            "roles": role_rows,
            "sources": research_sources or [],
            "decisions": decisions if decisions is not None else [{"action": "dispatch"}],
            "usage": {
                "total": 1,
                "by_role": {"supervisor": 1},
                "redirect_total": 0,
                "redirect_by_role": {},
            },
        },
    }


def _run_fake_verifier(report, monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, path, headers=None):
            calls.append(("GET", path, headers))
            if path == "/api/ready":
                return httpx.Response(200, json={"database": True, "broker": True})
            if headers is None:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "mode": "evidence_review",
                    "report": report,
                },
            )

        def post(self, path, json):
            calls.append(("POST", path, json))
            assert json["url"] == "https://product.example/item"
            return httpx.Response(
                202,
                json={
                    "id": "b20332d8-f137-4bf8-943a-0ecb4f7b82fa",
                    "access_token": "secret",
                    "status": "queued",
                },
            )

    monkeypatch.setattr("sys.argv", ["verify_research_live.py"])
    assert verify_research_live.main() == 0
    assert calls == []
    result = verify(
        "http://127.0.0.1:8000", "https://product.example/item", client_factory=FakeClient
    )
    return result, calls


def test_live_verifier_default_makes_no_requests_and_opt_in_one_post(monkeypatch):
    research_source = {
        "id": "research-1",
        "kind": "official",
        "access_scope": "document",
        "title": "Official source",
        "provider": "mock",
    }
    result, calls = _run_fake_verifier(
        _research_report(research_sources=[research_source]), monkeypatch
    )
    assert result["live"] == "passed"
    assert sum(call[0] == "POST" for call in calls) == 1
    assert "secret" not in repr(result)


def test_live_verifier_m1_root_sources_do_not_demonstrate_research(monkeypatch):
    m1_source = {"id": "m1-page", "title": "Product page", "url": "https://product.example/item"}
    result, _ = _run_fake_verifier(_research_report(m1_sources=[m1_source]), monkeypatch)
    assert result["analysis"]["source_count"] == 0
    assert result["analysis"]["research_observation"] == "not_demonstrated"
    assert result["checks"]["research_dispatch_and_read_observed"] is False


def test_live_verifier_research_discovery_only_is_not_demonstrated(monkeypatch):
    discovery = {
        "id": "discovery-1",
        "kind": "discovery",
        "access_scope": "discovery",
        "title": "Search result",
        "provider": "mock",
    }
    result, _ = _run_fake_verifier(_research_report(research_sources=[discovery]), monkeypatch)
    assert result["analysis"]["research_observation"] == "not_demonstrated"
    assert result["checks"]["research_dispatch_and_read_observed"] is False


@pytest.mark.parametrize("kind,scope", [("research", "abstract"), ("official", "document")])
def test_live_verifier_recognizes_nested_research_reads(monkeypatch, kind, scope):
    source = {
        "id": "read-1",
        "kind": kind,
        "access_scope": scope,
        "title": "Read source",
        "provider": "mock",
    }
    result, _ = _run_fake_verifier(_research_report(research_sources=[source]), monkeypatch)
    assert result["analysis"]["research_observation"] == "demonstrated"
    assert result["analysis"]["read_source_metadata"][0]["access_scope"] == scope


def test_live_verifier_rejects_duplicate_role_rows(monkeypatch):
    report = _research_report(
        research_sources=[
            {
                "id": "read-1",
                "kind": "research",
                "access_scope": "abstract",
                "title": "Read",
            }
        ]
    )
    report["research"]["roles"].append(dict(report["research"]["roles"][0]))
    result, _ = _run_fake_verifier(report, monkeypatch)
    assert result["checks"]["five_expected_roles"] is False
    assert result["live"] == "failed"


def test_live_verifier_checks_nested_research_source_text_is_not_public(monkeypatch):
    source = {
        "id": "read-1",
        "kind": "research",
        "access_scope": "abstract",
        "title": "Read source",
        "provider": "mock",
        "text": "private source text",
    }
    result, _ = _run_fake_verifier(_research_report(research_sources=[source]), monkeypatch)
    assert result["checks"]["public_sources_hide_text"] is False
    assert result["analysis"]["public_source_text_exposed"] is True
    assert "private source text" not in repr(result)
