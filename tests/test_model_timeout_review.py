"""Independent checks for the dedicated extraction timeout contract."""

from types import SimpleNamespace

import pytest

from supplement_advisor.agents import collection_graph as runtime
from supplement_advisor.agents import run_collection_graph
from supplement_advisor.collection import CollectedPage
from supplement_advisor.config import Settings


@pytest.fixture
def page():
    return CollectedPage(
        url="https://shop.example/product",
        title="표시 제품",
        text="제품명: 표시 제품 제조사: 표시 제조사 신고번호: 12345",
        html="<p>표시 제품</p>",
        image_urls=[],
    )


async def test_dedicated_model_timeout_is_reserved_and_cannot_exceed_it(page, monkeypatch):
    reservations = []
    settings = SimpleNamespace(
        openai_api_key="mock-key",
        openai_model="gpt-5.6-luna",
        model_timeout_seconds=30,
        external_timeout_seconds=15,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
        food_safety_api_key=None,
        reserve_budget=lambda **kwargs: reservations.append(kwargs) or True,
    )
    clients = []

    class CapturingClient:
        def __init__(self, **kwargs):
            clients.append(kwargs)
            self.responses = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def parse(self, **kwargs):
            return SimpleNamespace(output_parsed=None)

    monkeypatch.setattr(runtime, "AsyncOpenAI", CapturingClient)
    report = await run_collection_graph(page, None, settings)

    assert clients == [{"api_key": "mock-key", "timeout": 30.0, "max_retries": 0}]
    assert reservations[0] == {"seconds": 30.0, "tool_calls": 1}
    assert settings.external_timeout_seconds == 15
    assert report["extraction_status"] == {"code": "invalid_response"}
    assert report["score"] is None and report["verdict"] == "hold"


async def test_budget_rejection_prevents_model_request(page, monkeypatch):
    settings = SimpleNamespace(
        openai_api_key="mock-key",
        openai_model="gpt-5.6-luna",
        model_timeout_seconds=30,
        external_timeout_seconds=15,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
        food_safety_api_key=None,
        reserve_budget=lambda **kwargs: False,
    )

    class UnexpectedClient:
        def __init__(self, **kwargs):
            raise AssertionError("model request must not start without reserved budget")

    monkeypatch.setattr(runtime, "AsyncOpenAI", UnexpectedClient)
    report = await run_collection_graph(page, None, settings)
    assert report["extraction_status"] == {"code": "budget_exhausted"}
    assert report["score"] is None and report["verdict"] == "hold"


def test_timeout_bounds_and_legacy_external_timeout_are_unchanged():
    defaults = Settings(_env_file=None)
    assert defaults.model_timeout_seconds == 30
    assert defaults.external_timeout_seconds == 15
    assert defaults.analysis_timeout_seconds == 180
    assert defaults.attempt_timeout_seconds == 60
    assert defaults.max_tool_calls == 20
    for value in (0, 30.01):
        with pytest.raises(ValueError):
            Settings(_env_file=None, model_timeout_seconds=value)
