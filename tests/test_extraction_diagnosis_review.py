"""Independent safety regressions for typed extraction failure diagnostics."""

import hashlib
import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from supplement_advisor.agents import collection_graph as runtime
from supplement_advisor.collection import CollectedPage

ALLOWED_CODES = {
    "extracted",
    "not_configured",
    "budget_exhausted",
    "timeout",
    "authentication_failed",
    "permission_denied",
    "rate_limited",
    "connection_failed",
    "provider_error",
    "invalid_response",
    "incomplete",
    "refused",
    "request_failed",
}


def _sdk_errors():
    request = httpx.Request("POST", "https://api.example.test/v1/responses")
    response = httpx.Response(
        429,
        request=request,
        headers={"x-secret-header": "diagnostic-secret"},
        json={"error": {"message": "diagnostic-secret private payload"}},
    )
    return [
        (openai.APITimeoutError(request), "timeout"),
        (openai.AuthenticationError("diagnostic-secret", response=response, body=response.json()), "authentication_failed"),
        (openai.PermissionDeniedError("diagnostic-secret", response=response, body=response.json()), "permission_denied"),
        (openai.RateLimitError("diagnostic-secret", response=response, body=response.json()), "rate_limited"),
        (openai.APIConnectionError(message="diagnostic-secret", request=request), "connection_failed"),
        (openai.InternalServerError("diagnostic-secret", response=response, body=response.json()), "provider_error"),
        (openai.APIStatusError("diagnostic-secret", response=response, body=response.json()), "invalid_response"),
        (openai.BadRequestError("diagnostic-secret", response=response, body=response.json()), "invalid_response"),
        (openai.ContentFilterFinishReasonError(), "refused"),
        (openai.APIResponseValidationError(response, response.json(), message="diagnostic-secret"), "invalid_response"),
        (ValueError("diagnostic-secret"), "request_failed"),
    ]


@pytest.mark.parametrize("error,expected", _sdk_errors())
def test_sdk_failures_map_to_allowlisted_codes_without_message_parsing(error, expected):
    code = runtime._exception_extraction_code(error)
    assert code == expected
    assert code in ALLOWED_CODES


def test_builtin_timeout_and_unknown_exception_have_safe_fallback_codes():
    assert runtime._exception_extraction_code(TimeoutError("diagnostic-secret")) == "timeout"
    assert runtime._exception_extraction_code(RuntimeError("diagnostic-secret")) == "request_failed"


def test_structured_response_distinguishes_refusal_incomplete_and_unclassified_none():
    refusal = SimpleNamespace(
        status="completed",
        output=[SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="private reason")])],
    )
    incomplete = SimpleNamespace(status="incomplete", output=[])
    unexplained_empty = SimpleNamespace(status="completed", output=[])
    assert runtime._response_extraction_code(refusal) == "refused"
    assert runtime._response_extraction_code(incomplete) == "incomplete"
    assert runtime._response_extraction_code(unexplained_empty) == "invalid_response"


async def test_report_keeps_safe_code_and_korean_reason_only(monkeypatch):
    secret = "diagnostic-secret"
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.example.test/v1/responses"),
        headers={"x-private": secret},
        json={"error": {"message": secret, "body": secret}},
    )

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.responses = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def parse(self, **kwargs):
            raise openai.RateLimitError(secret, response=response, body=response.json())

    monkeypatch.setattr(runtime, "AsyncOpenAI", Client)
    page = CollectedPage(
        url="https://shop.example/product?private=secret",
        title="제품 페이지",
        text="표시 정보",
        html="<p>표시 정보</p>",
        image_urls=[],
    )
    settings = SimpleNamespace(
        openai_api_key="configured-key",
        openai_model="gpt-5.6-luna",
        food_safety_api_key=None,
        external_timeout_seconds=15,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
    )

    report = await runtime.run_collection_graph(page, None, settings)
    serialized = json.dumps(report, ensure_ascii=False)
    assert report["extraction_status"] == {"code": "rate_limited"}
    assert report["checks"][1]["status"] == "unavailable"
    assert "요청 한도" in report["checks"][1]["detail"]
    assert secret not in serialized
    assert "private" not in serialized
    assert report["score"] is None and report["verdict"] == "hold"


async def test_none_reasoning_retries_previous_timeout_snapshot_as_safe_timeout(monkeypatch):
    page = CollectedPage(
        url="https://shop.example/product",
        title="제품 페이지",
        text="제품명: 검사 대상 제품",
        html="<p>제품명: 검사 대상 제품</p>",
        image_urls=[],
    )
    fingerprint = hashlib.sha256(
        json.dumps([page.url, page.text, None], ensure_ascii=False).encode()
    ).hexdigest()
    saved_snapshots = []
    settings = SimpleNamespace(
        openai_api_key="configured-key",
        openai_model="gpt-5.6-luna",
        food_safety_api_key=None,
        external_timeout_seconds=15,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
        graph_snapshot={
            "version": 8,
            "fingerprint": fingerprint,
            "source": {"id": "old-source"},
            "extraction": None,
            "extraction_code": "timeout",
            "official": {},
            "report": {"stale": True},
        },
        save_snapshot=lambda snapshot: saved_snapshots.append(snapshot),
    )
    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.responses = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def parse(self, **kwargs):
            calls.append(kwargs)
            raise openai.APITimeoutError(
                httpx.Request("POST", "https://api.example.test/v1/responses")
            )

    monkeypatch.setattr(runtime, "AsyncOpenAI", Client)
    report = await runtime.run_collection_graph(page, None, settings)

    assert len(calls) == 1
    assert calls[0]["reasoning"] == {"effort": "none"}
    assert calls[0]["model"] == "gpt-5.6-luna"
    assert calls[0]["max_output_tokens"] == 4_000
    assert calls[0]["store"] is False
    assert calls[0]["text_format"] is runtime.Extraction
    assert "검사 대상 제품" in calls[0]["input"][1]["content"]
    assert report["extraction_status"] == {"code": "timeout"}
    assert report["checks"][1]["status"] == "unavailable"
    assert report["score"] is None and report["verdict"] == "hold"
    assert saved_snapshots and all(item["version"] == 10 for item in saved_snapshots)
