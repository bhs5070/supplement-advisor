"""Mocked checks for the one-batch supplement workflow; no live API access."""

import json
from types import SimpleNamespace

import httpx

from supplement_advisor.agents import run_supplement_graph


def base_report():
    return {
        "scope": "collection_only",
        "product": {"name": "페이지 제품", "manufacturer": None, "report_number": None},
        "claims": ["원문 주장"],
        "ingredients": [{"name": "페이지 성분", "amount": None, "unit": None, "basis": None}],
        "sources": [{"id": "product-page", "url": "https://shop.example/p", "title": "판매 페이지", "kind": "advertising"}],
        "checks": [{"name": "공식 등록 대조", "status": "unverified", "detail": "이전 결과", "source_ids": []}],
        "limitations": [],
        "missing_fields": ["manufacturer", "report_number"],
        "score": None,
        "verdict": "hold",
    }


def settings():
    return SimpleNamespace(
        food_safety_api_key=None,
        external_timeout_seconds=5,
        analysis_timeout_seconds=20,
        max_tool_calls=20,
    )


def official_mock(monkeypatch, rows):
    requests = []

    def handler(request):
        requests.append(request)
        body = json.dumps({"I0030": {"RESULT": {"CODE": "INFO-000"}, "row": rows}})
        return httpx.Response(200, stream=httpx.ByteStream(body.encode()))

    monkeypatch.setattr(
        "supplement_advisor.agents.collection_graph.httpx.AsyncHTTPTransport",
        lambda **kwargs: httpx.MockTransport(handler),
    )
    return requests


async def test_supplement_uses_user_identity_and_preserves_provenance(monkeypatch):
    config = settings()
    config.food_safety_api_key = "mock-key"
    requests = official_mock(
        monkeypatch,
        [{"PRDLST_NM": "보완 제품", "BSSH_NM": "보완 제조사", "PRDLST_REPORT_NO": "00123", "LAST_UPDT_DTM": "20261101"}],
    )
    result = await run_supplement_graph(
        base_report(),
        {
            "product_name": "보완 제품",
            "manufacturer": "보완 제조사",
            "report_number": "00123",
            "ingredients": [{"name": "비타민C", "amount": "100", "unit": "mg", "basis": None}],
        },
        config,
        received_at="2026-11-09T00:00:00+00:00",
    )
    assert len(requests) == 1
    assert result["product"]["name"] == "보완 제품"
    assert result["product"]["field_sources"] == {
        "name": "user-input", "manufacturer": "user-input", "report_number": "user-input"
    }
    assert result["ingredients"] == [{"name": "비타민C", "amount": "100", "unit": "mg", "basis": None, "source_id": "user-input"}]
    assert result["sources"][0]["id"] == "product-page"
    assert result["sources"][1] == {
        "id": "user-input", "url": "", "title": "사용자 추가 입력", "kind": "user_input",
        "retrieved_at": "2026-11-09T00:00:00+00:00",
        "excerpt": "사용자 제공: 제품명=보완 제품; 제조사=보완 제조사; 신고번호=00123; 성분=비타민C"
    }
    official_check = next(c for c in result["checks"] if c["name"] == "공식 등록 대조")
    assert official_check["status"] == "verified"
    assert "사용자 보완 식별 정보" in official_check["detail"]
    assert "실제 함량" in official_check["detail"]
    assert "report_number" not in result["missing_fields"]
    assert result["score"] is None and result["verdict"] == "hold"


async def test_missing_key_is_unavailable_and_second_request_is_not_offered():
    result = await run_supplement_graph(
        base_report(), {"manufacturer": "보완 제조사"}, settings()
    )
    official_check = next(c for c in result["checks"] if c["name"] == "공식 등록 대조")
    assert official_check["status"] == "unavailable"
    assert result["supplemental_input_used"] is True
    assert result["missing_fields"] == ["report_number"]
    assert "다시 요청하지 않습니다" in result["message"]


async def test_legacy_report_recomputes_missing_report_number_and_scope():
    legacy = base_report()
    legacy["missing_fields"] = []
    legacy["product"]["report_number"] = None
    legacy["scope"] = "full_evaluation"
    result = await run_supplement_graph(legacy, {"manufacturer": "보완 제조사"}, settings())
    assert result["scope"] == "collection_only"
    assert result["missing_fields"] == ["report_number"]
    assert "다시 요청하지 않습니다" in result["message"]
    assert "사용자 추가 입력" in result["limitations"][-1]


async def test_completed_official_result_reused_for_same_supplement(monkeypatch):
    config = settings()
    config.food_safety_api_key = "mock-key"
    requests = official_mock(monkeypatch, [])
    snapshots = []
    config.save_snapshot = lambda snapshot: snapshots.append(snapshot)
    arguments = (base_report(), {"manufacturer": "보완 제조사", "report_number": "00123"}, config)
    await run_supplement_graph(*arguments, received_at="2026-11-09T00:00:00+00:00")
    config.graph_snapshot = snapshots[0]
    config.save_snapshot = lambda snapshot: True
    await run_supplement_graph(*arguments, received_at="2026-11-09T00:00:00+00:00")
    assert len(requests) == 1


async def test_new_supplement_invalidates_prior_official_snapshot(monkeypatch):
    config = settings()
    config.food_safety_api_key = "mock-key"
    requests = official_mock(monkeypatch, [])
    snapshots = []
    config.save_snapshot = lambda snapshot: snapshots.append(snapshot)
    first = (base_report(), {"manufacturer": "제조사", "report_number": "00123"}, config)
    await run_supplement_graph(*first)
    config.graph_snapshot = snapshots[0]
    await run_supplement_graph(base_report(), {"manufacturer": "다른 제조사", "report_number": "00456"}, config)
    assert len(requests) == 2
