"""Behavioral coverage for the one-time guest supplement boundary."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from supplement_advisor.config import Settings
from supplement_advisor.database import make_engine, session_factory
from supplement_advisor.main import create_app
from supplement_advisor.models import Analysis, Base
from supplement_advisor.repository import get_analysis
from supplement_advisor.schemas import SupplementalInput


@pytest.fixture
def context(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'supplement.db'}",
        raw_storage_dir=tmp_path / "private",
        openai_api_key=None,
        food_safety_api_key=None,
    )
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)

    async def validate(_url):
        return None

    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    published = []
    client = TestClient(create_app(settings, engine=engine, dispatch=published.append))
    yield settings, engine, client, published
    client.close()
    engine.dispose()


def test_supplement_input_preserves_identifier_strings_and_rejects_empty():
    payload = SupplementalInput.model_validate(
        {"report_number": "00123456789", "ingredients": [{"name": "칼슘", "amount": "250", "unit": "mg", "basis": "1일 섭취량"}]}
    )
    assert payload.report_number == "00123456789"
    assert payload.ingredients[0].amount == "250"
    with pytest.raises(ValueError):
        SupplementalInput.model_validate({"product_name": "  ", "ingredients": [{"name": " "}]})
    with pytest.raises(ValueError):
        SupplementalInput.model_validate({"report_number": "１２３"})
    with pytest.raises(ValueError):
        SupplementalInput.model_validate({"report_number": "12-3"})
    with pytest.raises(ValueError):
        SupplementalInput.model_validate(
            {"manufacturer": "Company", "ingredients": [{"name": " "}]}
        )


def needs_input(context):
    settings, engine, client, published = context
    accepted = client.post("/api/analyses", json={"url": "https://example.com"}).json()
    with session_factory(engine).begin() as session:
        session.query(Analysis).filter_by(id=accepted["id"]).update(
            {"status": "needs_input", "report": {"scope": "collection_only", "missing_fields": ["report_number"]}, "message": "need input"}
        )
    return accepted


def test_supplement_authorization_state_and_persisted_flags(context):
    _, engine, client, published = context
    accepted = needs_input(context)
    path = f"/api/analyses/{accepted['id']}/supplement"
    body = {"report_number": "00102003004", "ingredients": [{"name": "Vitamin C", "amount": "500", "unit": "mg", "basis": "1회"}]}
    wrong = client.post(path, json=body, headers={"X-Analysis-Token": "wrong"})
    assert wrong.status_code == 404
    other_id = client.post(
        f"/api/analyses/{'00000000-0000-0000-0000-000000000000'}/supplement",
        json=body,
        headers={"X-Analysis-Token": accepted["access_token"]},
    )
    assert other_id.status_code == 404
    headers = {"X-Analysis-Token": accepted["access_token"]}
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 202
    assert response.json() == {"id": accepted["id"], "status": "queued"}
    assert "access_token" not in response.text
    assert client.post(path, json=body, headers=headers).status_code == 409
    result = client.get(f"/api/analyses/{accepted['id']}", headers=headers).json()
    assert result["supplemental_input_used"] is True
    assert result["can_supplement"] is False
    with session_factory(engine)() as session:
        row = get_analysis(session, accepted["id"])
        assert row.supplemental_input["report_number"] == "00102003004"
        assert row.supplemental_received_at is not None
        assert row.status == "queued" and row.graph_snapshot is None
        assert row.report["missing_fields"] == ["report_number"]
        assert row.attempt_count == row.active_seconds_reserved == row.tool_calls_reserved == 0
    assert published[-1] == accepted["id"]


def test_simultaneous_supplements_have_one_winner(context):
    _, _, client, _ = context
    accepted = needs_input(context)
    barrier = Barrier(2)
    body = {"manufacturer": "제조사"}
    headers = {"X-Analysis-Token": accepted["access_token"]}

    def submit():
        barrier.wait()
        return client.post(
            f"/api/analyses/{accepted['id']}/supplement", json=body, headers=headers
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(submit), pool.submit(submit)]
        statuses = sorted(f.result() for f in results)
    assert statuses == [202, 409]


def test_publish_failure_keeps_supplement_dispatchable(context):
    settings, engine, _, _ = context
    accepted = needs_input(context)

    def fail(_):
        raise ConnectionError("broker unavailable")

    client = TestClient(__import__("supplement_advisor.main", fromlist=["create_app"]).create_app(settings, engine=engine, dispatch=fail))
    result = client.post(
        f"/api/analyses/{accepted['id']}/supplement",
        json={"product_name": "제품"},
        headers={"X-Analysis-Token": accepted["access_token"]},
    )
    assert result.status_code == 202
    from supplement_advisor.repository import list_dispatchable

    with session_factory(engine)() as session:
        assert list_dispatchable(session) == [accepted["id"]]
    client.close()


async def test_worker_uses_saved_report_and_preserves_cumulative_budget_and_raw_file(
    context, monkeypatch
):
    settings, engine, client, _ = context
    accepted = needs_input(context)
    with session_factory(engine).begin() as session:
        session.query(Analysis).filter_by(id=accepted["id"]).update(
            {
                "raw_file": "private/original.html",
                "attempt_count": 1,
                "active_seconds_reserved": 60,
                "tool_calls_reserved": 4,
            }
        )
    headers = {"X-Analysis-Token": accepted["access_token"]}
    response = client.post(
        f"/api/analyses/{accepted['id']}/supplement",
        json={"report_number": "001234"},
        headers=headers,
    )
    assert response.status_code == 202
    graph_args = []

    async def no_collection(*_args, **_kwargs):
        pytest.fail("Supplement processing must not re-fetch the source page")

    async def supplement(report, information, runtime, *, received_at=None):
        graph_args.append((report, information, received_at))
        assert runtime.graph_snapshot is None
        assert runtime.reserve_budget(0, 2)
        return {**report, "missing_fields": [], "supplemental_input_used": True}

    from supplement_advisor.tasks import execute_analysis

    monkeypatch.setattr("supplement_advisor.tasks.collect_page", no_collection)
    monkeypatch.setattr("supplement_advisor.agents.run_supplement_graph", supplement)
    await execute_analysis(accepted["id"], settings)
    with session_factory(engine)() as session:
        row = get_analysis(session, accepted["id"])
        assert row.status == "completed"
        assert row.attempt_count == 2
        assert row.active_seconds_reserved == 120
        assert row.tool_calls_reserved == 6
        assert row.raw_file == "private/original.html"
    assert graph_args[0][0]["missing_fields"] == ["report_number"]
    assert graph_args[0][1]["report_number"] == "001234"
    assert graph_args[0][2]
