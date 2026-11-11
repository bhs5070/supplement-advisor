"""Independent regression probes for supplement failure data retention."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from supplement_advisor.agents import run_supplement_graph
from supplement_advisor.config import Settings
from supplement_advisor.database import make_engine, session_factory
from supplement_advisor.main import create_app
from supplement_advisor.models import Analysis
from supplement_advisor.repository import get_analysis
from supplement_advisor.schemas import SupplementalIngredient


@pytest.fixture
def context(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'supplement-review.db'}",
        raw_storage_dir=tmp_path / "private",
        openai_api_key=None,
        food_safety_api_key=None,
    )
    engine = make_engine(settings.database_url)
    Analysis.metadata.create_all(engine)

    async def validate(_url):
        return None

    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    client = TestClient(create_app(settings, engine=engine, dispatch=lambda _: None))
    yield settings, engine, client
    client.close()
    engine.dispose()


def test_blank_optional_ingredient_values_normalize_to_null():
    ingredient = SupplementalIngredient.model_validate(
        {"name": "Vitamin C", "amount": " ", "unit": "\t", "basis": "  "}
    )
    assert ingredient.amount is None
    assert ingredient.unit is None
    assert ingredient.basis is None


async def test_supplement_budget_exhaustion_preserves_existing_report(context):
    settings, engine, client = context
    accepted = client.post(
        "/api/analyses", json={"url": "https://example.com"}
    ).json()
    original_report = {
        "scope": "collection_only",
        "product": {"name": "Original product"},
        "missing_fields": ["report_number"],
    }
    with session_factory(engine).begin() as session:
        session.query(Analysis).filter_by(id=accepted["id"]).update(
            {
                "status": "needs_input",
                "report": original_report,
                "active_seconds_reserved": 150,
            }
        )

    response = client.post(
        f"/api/analyses/{accepted['id']}/supplement",
        json={"report_number": "001234"},
        headers={"X-Analysis-Token": accepted["access_token"]},
    )
    assert response.status_code == 202

    from supplement_advisor.tasks import execute_analysis

    await execute_analysis(accepted["id"], settings)
    with session_factory(engine)() as session:
        row = get_analysis(session, accepted["id"])
        assert row.status == "failed"
        assert row.error_code == "budget_exhausted"
        assert row.report == original_report


def report_with_identity():
    return {
        "scope": "collection_only",
        "product": {"name": "Page name", "manufacturer": "Page maker", "report_number": "00123"},
        "ingredients": [{"name": "Page ingredient", "amount": None, "unit": None, "basis": None}],
        "sources": [{"id": "product-page", "url": "https://shop.example", "kind": "advertising"}],
        "checks": [],
        "limitations": [],
        "missing_fields": [],
        "score": None,
        "verdict": "hold",
    }


def official_response(monkeypatch):
    def handler(_request):
        body = json.dumps({"I0030": {"RESULT": {"CODE": "INFO-000"}, "row": [
            {"PRDLST_NM": "Page name", "BSSH_NM": "Page maker", "PRDLST_REPORT_NO": "00123", "LAST_UPDT_DTM": "20261101"}
        ]}})
        return httpx.Response(200, stream=httpx.ByteStream(body.encode()))

    monkeypatch.setattr(
        "supplement_advisor.agents.collection_graph.httpx.AsyncHTTPTransport",
        lambda **kwargs: httpx.MockTransport(handler),
    )


def graph_settings():
    return SimpleNamespace(
        food_safety_api_key="mock-key", external_timeout_seconds=5,
        analysis_timeout_seconds=20, max_tool_calls=20,
    )


async def test_ingredients_only_supplement_does_not_claim_identity_was_user_provided(monkeypatch):
    official_response(monkeypatch)
    result = await run_supplement_graph(
        report_with_identity(), {"ingredients": [{"name": "Manual ingredient", "amount": None, "unit": None, "basis": None}]}, graph_settings()
    )
    check = next(item for item in result["checks"] if item["name"] == "공식 등록 대조")
    assert "수집 정보" in check["detail"]
    # Candidate rows carry their own source IDs; every cited ID must resolve in sources.
    source_ids = {item["id"] for item in result["sources"]}
    assert "product-page" in check["source_ids"]
    assert "user-input" not in check["source_ids"]
    assert any(item.startswith("official-i0030") for item in check["source_ids"])
    assert set(check["source_ids"]) <= source_ids


async def test_report_number_only_supplement_cites_page_and_user_identity_sources(monkeypatch):
    official_response(monkeypatch)
    result = await run_supplement_graph(
        report_with_identity(), {"report_number": "00123"}, graph_settings()
    )
    check = next(item for item in result["checks"] if item["name"] == "공식 등록 대조")
    # The check cites page + supplied identity + every official candidate source.
    source_ids = {item["id"] for item in result["sources"]}
    assert "product-page" in check["source_ids"]
    assert "user-input" in check["source_ids"]
    assert any(item.startswith("official-i0030") for item in check["source_ids"])
    assert set(check["source_ids"]) <= source_ids


async def test_report_limitation_does_not_expose_implementation_field_names():
    result = await run_supplement_graph(
        report_with_identity(), {"report_number": "00123"}, graph_settings()
    )
    limitation = result["limitations"][-1]
    assert "field_sources" not in limitation
    assert "source_id" not in limitation
    assert "사용자" in limitation
