"""API and task integration with real code, isolated DB and mocked network only."""

import asyncio
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from supplement_advisor.collection import CollectedPage, CollectionError
from supplement_advisor.config import Settings
from supplement_advisor.database import make_engine, session_factory
from supplement_advisor.main import create_app
from supplement_advisor.models import Analysis, Base
from supplement_advisor.repository import claim_analysis, get_analysis, reserve_budget
from supplement_advisor.tasks import execute_analysis


def test_analysis_task_time_limits_match_the_durable_attempt_window():
    from supplement_advisor.celery_app import celery_app
    from supplement_advisor.tasks import process_analysis

    annotations = celery_app.conf.task_annotations[process_analysis.name]
    from supplement_advisor.config import get_settings

    settings = get_settings()
    durable_window = min(settings.attempt_timeout_seconds, settings.analysis_timeout_seconds)
    assert annotations["time_limit"] == durable_window
    assert annotations["soft_time_limit"] < annotations["time_limit"]
    assert celery_app.conf.task_time_limit == 80  # recover_pending keeps its separate default


@pytest.fixture
def context(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        raw_storage_dir=tmp_path / "private",
        openai_api_key=None,
        food_safety_api_key=None,
    )
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)

    async def validated(url):
        if "127.0.0.1" in url:
            raise CollectionError("unsafe_url", "공개 인터넷 주소만 수집할 수 있습니다.")

    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validated)
    published = []
    client = TestClient(create_app(settings, engine=engine, dispatch=published.append))
    yield settings, engine, client, published
    client.close()
    engine.dispose()


def test_guest_tokens_isolate_results_and_never_return_storage_details(context):
    settings, engine, client, published = context
    first = client.post("/api/analyses", json={"url": "https://example.com/?secret=hidden"})
    second = client.post("/api/analyses", json={"url": "https://example.org"})
    assert first.status_code == second.status_code == 202
    first, second = first.json(), second.json()
    assert published == [first["id"], second["id"]]
    for identity, token in [
        (first["id"], None),
        (first["id"], second["access_token"]),
        ("invalid", "x"),
    ]:
        response = client.get(
            f"/api/analyses/{identity}", headers={"X-Analysis-Token": token} if token else {}
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "결과를 찾을 수 없습니다."}
    response = client.get(
        f"/api/analyses/{first['id']}", headers={"X-Analysis-Token": first["access_token"]}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert (
        "hidden" not in response.text
        and "token" not in response.text
        and "raw_file" not in response.text
    )
    with session_factory(engine)() as session:
        row = get_analysis(session, first["id"])
        assert row.token_hash == hashlib.sha256(first["access_token"].encode()).hexdigest()


def test_invalid_input_and_capabilities_do_not_expose_input_or_secrets(context):
    settings, engine, client, published = context
    assert client.post("/api/analyses", json={"url": "http://127.0.0.1"}).status_code == 422
    result = client.post("/api/analyses", json={"url": "private-input" * 1000})
    assert result.status_code == 422 and "private-input" not in result.text
    capabilities = client.get("/api/capabilities").json()
    assert capabilities["openai"] == capabilities["food_safety"] == "not_configured"
    assert capabilities["personal_suitability"] == "not_evaluated"


def test_publish_failure_preserves_queued_request_for_recovery(context):
    settings, engine, _, _ = context

    def fail_publish(identity):
        raise ConnectionError("broker unavailable")

    client = TestClient(create_app(settings, engine=engine, dispatch=fail_publish))
    response = client.post("/api/analyses", json={"url": "https://example.com"})
    assert response.status_code == 202
    with session_factory(engine)() as session:
        assert get_analysis(session, response.json()["id"]).status == "queued"


def test_broker_publication_does_not_block_the_api_event_loop(context):
    settings, engine, _, _ = context

    def delayed_publish(identity):
        import time
        time.sleep(0.5)

    client = TestClient(create_app(settings, engine=engine, dispatch=delayed_publish))

    async def exercise():
        import httpx
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            submitting = asyncio.create_task(http.post("/api/analyses", json={"url": "https://example.com"}))
            await asyncio.sleep(0.02)
            assert not submitting.done()
            await submitting

    asyncio.run(exercise())
    client.close()


def test_oversized_guest_token_has_same_not_found_response(context):
    _, _, client, _ = context
    accepted = client.post("/api/analyses", json={"url": "https://example.com"}).json()
    response = client.get(
        f"/api/analyses/{accepted['id']}", headers={"X-Analysis-Token": "x" * 257}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "결과를 찾을 수 없습니다."}


async def test_worker_persists_graph_report_and_duplicate_is_noop(context, monkeypatch):
    settings, engine, client, _ = context
    calls = []

    async def collect(url, **kwargs):
        calls.append(url)
        return CollectedPage(url, "제품 페이지", "표시 정보 없음", "<title>제품 페이지</title>", [])

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", collect)
    accepted = client.post("/api/analyses", json={"url": "https://example.com"}).json()
    await execute_analysis(accepted["id"], settings)
    await execute_analysis(accepted["id"], settings)
    report = client.get(
        f"/api/analyses/{accepted['id']}", headers={"X-Analysis-Token": accepted["access_token"]}
    ).json()
    assert report["status"] == "needs_input"
    assert report["report"]["scope"] == "collection_only"
    assert report["report"]["score"] is None and report["report"]["verdict"] == "hold"
    assert len(calls) == 1
    with session_factory(engine)() as session:
        row = get_analysis(session, accepted["id"])
        assert row.attempt_count == 1 and row.active_seconds_reserved == 60
        assert row.tool_calls_reserved == 1 and row.graph_snapshot
        assert (settings.raw_storage_dir / row.raw_file).is_file()


async def test_collection_error_is_safe_and_terminal(context, monkeypatch):
    settings, engine, client, _ = context

    async def collect(url, **kwargs):
        raise CollectionError("unsafe_url", "공개 인터넷 주소만 수집할 수 있습니다.")

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", collect)
    accepted = client.post("/api/analyses", json={"url": "https://example.com"}).json()
    await execute_analysis(accepted["id"], settings)
    with session_factory(engine)() as session:
        row = get_analysis(session, accepted["id"])
        assert row.status == "failed" and row.error_code == "unsafe_url" and row.report is None


async def test_crash_recovery_preserves_previously_reserved_budget(context, monkeypatch):
    settings, engine, client, _ = context
    accepted = client.post("/api/analyses", json={"url": "https://example.com"}).json()
    from datetime import datetime, timedelta, timezone

    with session_factory(engine).begin() as session:
        claim = claim_analysis(session, accepted["id"])
        assert reserve_budget(
            session, accepted["id"], claim_token=claim.claim_token, seconds=150, tool_calls=19
        )
        session.execute(
            update(Analysis)
            .where(Analysis.id == claim.id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )

    async def must_not_collect(*args, **kwargs):
        pytest.fail("Work must not run after its durable budget is exhausted")

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", must_not_collect)
    await execute_analysis(accepted["id"], settings)
    with session_factory(engine)() as session:
        row = get_analysis(session, accepted["id"])
        assert row.status == "failed" and row.error_code == "budget_exhausted"
        assert row.active_seconds_reserved == 150 and row.tool_calls_reserved == 19
