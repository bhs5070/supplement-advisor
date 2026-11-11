"""Mock network tests; none of these establish model or official API access."""

import json
from types import SimpleNamespace

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from supplement_advisor.agents import collection_graph as runtime
from supplement_advisor.agents import run_collection_graph
from supplement_advisor.collection import CollectedPage
from supplement_advisor.config import Settings


@pytest.fixture
def settings():
    return SimpleNamespace(
        openai_api_key=None,
        openai_model="gpt-5.6-luna",
        food_safety_api_key=None,
        external_timeout_seconds=15,
        model_timeout_seconds=30,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
    )


@pytest.fixture
def page():
    return CollectedPage(
        url="https://shop.example/product?private-query=secret#fragment",
        title="표시 제품",
        text="제품명: 표시 제품 제조사: 표시 제조사 신고번호: 12345 비타민C 100 mg 1일 1정 항산화에 도움",
        html=("<p>제품명: 표시 제품</p><p>제조사: 표시 제조사</p>"
              "<p>신고번호: 12345</p><p>비타민C 100 mg 1일 1정</p>"),
        image_urls=["http://127.0.0.1/metadata"],
    )


def extraction():
    return runtime.Extraction.model_validate(
        {
            "product_name": {"value": "표시 제품", "excerpt": "제품명: 표시 제품"},
            "manufacturer": {"value": "표시 제조사", "excerpt": "제조사: 표시 제조사"},
            "report_number": {"value": "12345", "excerpt": "신고번호: 12345"},
            "claims": [
                {"value": "항산화에 도움", "excerpt": "항산화에 도움"},
                {"value": "치료 보장", "excerpt": "원문에 없는 근거"},
            ],
            "ingredients": [
                {
                    "name": "비타민C",
                    "amount": "100",
                    "unit": "mg",
                    "basis": "1일 1정",
                    "excerpt": "비타민C 100 mg 1일 1정",
                },
                {
                    "name": "비타민D",
                    "amount": "999",
                    "unit": "mg",
                    "basis": None,
                    "excerpt": "원문에 없는 성분",
                },
            ],
        }
    )


def fake_model(monkeypatch, value=None, error=None):
    requests = []
    options = []

    class Client:
        def __init__(self, **kwargs):
            options.append(kwargs)
            self.responses = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def parse(self, **kwargs):
            requests.append(kwargs)
            if error:
                raise error
            return SimpleNamespace(output_parsed=value)

    monkeypatch.setattr(runtime, "AsyncOpenAI", Client)
    return requests, options


def fake_official(monkeypatch, rows=None, code="INFO-000", status=200, data=None, total_count=None):
    requests = []

    def handler(request):
        requests.append(request)
        payload = {"I0030": {"RESULT": {"CODE": code}, "total_count": len(rows or []) if total_count is None else total_count, "row": rows or []}}
        content = json.dumps(payload).encode() if data is None else data
        return httpx.Response(status, stream=httpx.ByteStream(content))

    monkeypatch.setattr(
        runtime.httpx, "AsyncHTTPTransport", lambda **kw: httpx.MockTransport(handler)
    )
    return requests


def check(report, name):
    return next(item for item in report["checks"] if item["name"] == name)


async def test_without_keys_is_honest_and_queries_redacted(page, settings, monkeypatch):
    model, _ = fake_model(monkeypatch, error=AssertionError("No call expected"))
    official = fake_official(monkeypatch)
    report = await run_collection_graph(page, None, settings)
    assert not model and not official
    assert report["scope"] == "collection_only"
    assert report["score"] is None and report["verdict"] == "hold"
    assert report["ingredients"] == [] and report["claims"] == []
    assert check(report, "표시 정보 추출")["status"] == "unavailable"
    assert check(report, "공식 등록 대조")["status"] == "unavailable"
    assert check(report, "개인 적합성")["status"] == "not_applicable"
    assert report["sources"][0]["url"] == "https://shop.example/product"
    assert "private-query" not in json.dumps(report)
    assert "ingredient_label" in report["missing_fields"]


async def test_model_extracts_only_grounded_literals_and_keeps_units(page, settings, monkeypatch):
    settings.openai_api_key = "not-a-real-key"
    requests, options = fake_model(monkeypatch, extraction())
    report = await run_collection_graph(page, "입력 이름", settings)
    assert report["product"]["name"] == "표시 제품"
    assert report["product"]["submitted_name"] == "입력 이름"
    assert report["claims"] == ["항산화에 도움"]
    assert report["ingredients"] == [
        {"name": "비타민C", "amount": "100", "unit": "mg", "basis": "1일 1정"}
    ]
    assert options[0]["max_retries"] == 0
    assert options[0]["timeout"] == 30
    assert requests[0]["model"] == "gpt-5.6-luna"
    assert requests[0]["reasoning"] == {"effort": "none"}
    assert requests[0]["text_format"] is runtime.Extraction
    assert requests[0]["store"] is False and requests[0]["max_output_tokens"] == 4000
    assert "temperature" not in requests[0]
    assert requests[0]["input"][0]["role"] == "system"
    prompt = requests[0]["input"][0]["content"]
    assert "영양·기능정보 표" in prompt
    assert "원산지 표시는 성분명이나 섭취 기준에 넣지 않고" in prompt
    assert "상표명과 기능성 등록 코드는 성분명에 보존한다" in prompt
    assert "untrusted_document" in requests[0]["input"][1]["content"]
    assert "127.0.0.1" not in json.dumps(requests[0], default=str)


async def test_model_timeout_is_independent_and_enforced(page, settings, monkeypatch):
    settings.openai_api_key = "model-secret"
    settings.model_timeout_seconds = 0.01

    class SlowClient:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.responses = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def parse(self, **kwargs):
            await runtime.asyncio.sleep(0.05)

    monkeypatch.setattr(runtime, "AsyncOpenAI", SlowClient)
    report = await run_collection_graph(page, None, settings)
    assert report["extraction_status"] == {"code": "timeout"}
    assert settings.external_timeout_seconds == 15


def test_model_timeout_setting_is_bounded():
    assert Settings(_env_file=None).model_timeout_seconds == 30
    for value in (0, 31):
        with pytest.raises(ValueError):
            Settings(_env_file=None, model_timeout_seconds=value)


def test_amount_and_unit_substrings_do_not_turn_into_labeled_values():
    value = extraction()
    value.ingredients[0].amount = "10"
    value.ingredients[0].unit = "g"
    grounded = runtime._ground_extraction(value, "비타민C 100 mg 1일 1정")
    assert grounded["ingredients"][0]["amount"] is None
    assert grounded["ingredients"][0]["unit"] is None
    value.ingredients[0].amount = "100"
    value.ingredients[0].unit = "μg"
    value.ingredients[0].excerpt = "비타민C 100μg 1일 1정"
    grounded = runtime._ground_extraction(value, value.ingredients[0].excerpt)
    assert grounded["ingredients"][0]["amount"] == "100"
    assert grounded["ingredients"][0]["unit"] == "μg"


@pytest.mark.parametrize("placeholder", ["상세페이지 참조", "상세설명 참조", "상품상세 참조", "상품 상세 참조"])
def test_model_grounded_identity_placeholders_are_withheld(placeholder):
    text = f"제품명: {placeholder}"
    value = runtime.Extraction.model_validate({
        "product_name": {"value": placeholder, "excerpt": text},
        "manufacturer": None, "report_number": None, "claims": [], "ingredients": [],
    })
    grounded = runtime._ground_extraction(value, text, model_identity=True)
    assert grounded["product_name"] is None


@pytest.mark.parametrize(
    ("html", "text", "manufacturer", "expected"),
    [
        ('<table><tr><th>③ 제조업소의 명칭과 소재지</th><td>코스맥스엔비티(주)</td></tr></table>',
         "③ 제조업소의 명칭과 소재지 코스맥스엔비티(주)", "코스맥스엔비티(주)", "코스맥스엔비티(주)"),
        ('<table><tr><td>제조업소의 명칭과 소재지 제조원: 콜마비앤에이치(주)음성공장 / 충북 유통전문판매원: (주)플레이디</td></tr></table>',
         "제조업소의 명칭과 소재지 제조원: 콜마비앤에이치(주)음성공장 / 충북 유통전문판매원: (주)플레이디",
         "콜마비앤에이치(주)음성공장", "콜마비앤에이치(주)음성공장"),
        ('<p>제조원 및 판매원:(주)시나몬랩</p>', "제조원 및 판매원:(주)시나몬랩", "(주)시나몬랩", "(주)시나몬랩"),
        ('<p>판매원: 코스맥스엔비티(주)</p>', "판매원: 코스맥스엔비티(주)", "코스맥스엔비티(주)", None),
        ('<footer>코스맥스엔비티(주)</footer>', "코스맥스엔비티(주)", "코스맥스엔비티(주)", None),
        ('<p>제조원: 다른 제조사</p><p>코스맥스엔비티(주)</p>',
         "제조원: 다른 제조사 코스맥스엔비티(주)", "코스맥스엔비티(주)", None),
        ('<p>제조원: 콜마비앤에이치(주)음성공장</p>',
         "제조원: 콜마비앤에이치(주)음성공장", "콜마비앤에이치(주)", None),
    ],
)
def test_model_manufacturer_requires_same_source_row_or_paragraph_role(html, text, manufacturer, expected):
    extraction = runtime.Extraction.model_validate({
        "product_name": None,
        "manufacturer": {"value": manufacturer, "excerpt": manufacturer},
        "report_number": None, "claims": [], "ingredients": [],
    })
    grounded = runtime._ground_extraction(extraction, text, model_identity=True, source_html=html)
    assert grounded["manufacturer"] == expected


@pytest.mark.parametrize("amount", ["1", "000"])
def test_thousands_separator_does_not_turn_amount_substring_into_value(amount):
    value = extraction()
    value.ingredients[0].name = "비타민C"
    value.ingredients[0].amount = amount
    value.ingredients[0].unit = "mg"
    value.ingredients[0].excerpt = "비타민C 1,000 mg"
    grounded = runtime._ground_extraction(value, "비타민C 1,000 mg")
    assert grounded["ingredients"][0]["amount"] is None


def test_full_thousands_amount_is_preserved():
    value = extraction()
    value.ingredients[0].amount = "1,000"
    value.ingredients[0].excerpt = "비타민C 1,000 mg"
    grounded = runtime._ground_extraction(value, "비타민C 1,000 mg")
    assert grounded["ingredients"][0]["amount"] == "1,000"


async def test_name_only_official_hit_does_not_identify_product(page, settings, monkeypatch):
    settings.food_safety_api_key = "official-secret"
    requests = fake_official(
        monkeypatch,
        [{"PRDLST_NM": "표시 제품", "BSSH_NM": "다른 제조사", "PRDLST_REPORT_NO": "999"}],
    )
    report = await run_collection_graph(page, "표시 제품", settings)
    assert len(requests) == 2
    assert requests[0].url.scheme == "https"
    assert "/PRDLST_NM=%ED%91%9C%EC%8B%9C%20%EC%A0%9C%ED%92%88" in str(requests[0].url)
    assert check(report, "공식 등록 대조")["status"] == "unverified"
    assert "미등록 또는 불법이라는 의미가 아닙니다" in check(report, "공식 등록 대조")["detail"]
    assert "official-secret" not in json.dumps(report, ensure_ascii=False)


async def test_official_identity_requires_name_manufacturer_and_report_number(
    page, settings, monkeypatch
):
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    fake_model(monkeypatch, extraction())
    requests = fake_official(
        monkeypatch,
        [
            {
                "PRDLST_NM": "표시 제품",
                "BSSH_NM": "표시 제조사",
                "PRDLST_REPORT_NO": "12345",
                "LAST_UPDT_DTM": "20261101",
            }
        ],
    )
    report = await run_collection_graph(page, None, settings)
    assert len(requests) == 1
    assert "/PRDLST_REPORT_NO=12345" in str(requests[0].url)
    assert check(report, "공식 등록 대조")["status"] == "verified"
    assert report["sources"][1]["kind"] == "official"
    assert report["sources"][1]["document_id"] == "12345"
    assert report["sources"][1]["version"] == "20261101"
    assert (
        "실제 함량·효과·개인 안전성을 보증하지 않습니다"
        in check(report, "공식 등록 대조")["detail"]
    )
    assert report["score"] is None
    assert report["official_match"]["state"] == "matched"
    assert report["official_match"]["matched_record"]["PRDLST_REPORT_NO"] == "12345"


@pytest.mark.parametrize(
    "manufacturer,number", [("다른 제조사", "12345"), ("표시 제조사", "999"), ("표시 제조사", "")]
)
async def test_partial_identity_is_unverified(page, settings, monkeypatch, manufacturer, number):
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    fake_model(monkeypatch, extraction())
    fake_official(
        monkeypatch,
        [{"PRDLST_NM": "표시 제품", "BSSH_NM": manufacturer, "PRDLST_REPORT_NO": number}],
    )
    report = await run_collection_graph(page, None, settings)
    assert check(report, "공식 등록 대조")["status"] == "unverified"


async def test_call_failures_are_unavailable_without_exception_or_key(page, settings, monkeypatch):
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    fake_model(monkeypatch, error=RuntimeError("private https://bad.example/?secret=model-secret"))
    fake_official(monkeypatch, status=500)
    report = await run_collection_graph(page, "표시 제품", settings)
    assert check(report, "표시 정보 추출")["status"] == "unavailable"
    assert check(report, "공식 등록 대조")["status"] == "unavailable"
    serialized = json.dumps(report)
    assert "model-secret" not in serialized and "official-secret" not in serialized
    assert "bad.example" not in serialized


@pytest.mark.parametrize(
    ("error_factory", "expected"),
    [
        (lambda request, response: runtime.APITimeoutError(request), "timeout"),
        (lambda request, response: runtime.AuthenticationError("secret token", response=response, body={"secret": "body"}), "authentication_failed"),
        (lambda request, response: runtime.PermissionDeniedError("private detail", response=response, body={"secret": "body"}), "permission_denied"),
        (lambda request, response: runtime.RateLimitError("private detail", response=response, body={"secret": "body"}), "rate_limited"),
        (lambda request, response: runtime.APIConnectionError(message="https://private.example/?key=secret", request=request), "connection_failed"),
        (lambda request, response: runtime.InternalServerError("private response", response=response, body={"secret": "body"}), "provider_error"),
        (lambda request, response: runtime.APIResponseValidationError(response, {"secret": "body"}), "invalid_response"),
        (lambda request, response: runtime.BadRequestError("private response", response=response, body={"secret": "body"}), "invalid_response"),
        (lambda request, response: runtime.LengthFinishReasonError(completion=SimpleNamespace(usage=None)), "incomplete"),
        (lambda request, response: runtime.ContentFilterFinishReasonError(), "refused"),
        (lambda request, response: RuntimeError("https://private.example/?key=secret body=private"), "request_failed"),
    ],
)
async def test_typed_extraction_failures_store_only_safe_code(
    page, settings, monkeypatch, error_factory, expected
):
    settings.openai_api_key = "model-secret"
    request = httpx.Request("POST", "https://api.openai.com/v1/responses?token=private")
    response = httpx.Response(500, request=request)
    fake_model(monkeypatch, error=error_factory(request, response))
    report = await run_collection_graph(page, None, settings)
    serialized = json.dumps(report, ensure_ascii=False)
    assert report["extraction_status"] == {"code": expected}
    assert check(report, "표시 정보 추출")["status"] == "unavailable"
    assert "private.example" not in serialized
    assert "model-secret" not in serialized and "private" not in serialized


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (SimpleNamespace(status="incomplete", output=[], output_parsed=None), "incomplete"),
        (SimpleNamespace(status="completed", output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])], output_parsed=None), "refused"),
        (SimpleNamespace(status="completed", output=[], output_parsed=None), "invalid_response"),
    ],
)
async def test_structured_extraction_response_failure_codes(page, settings, monkeypatch, response, expected):
    settings.openai_api_key = "model-secret"
    fake_model(monkeypatch, value=None)
    # Keep the response's structured status tags; no free-form detail is inspected.
    class Client:
        def __init__(self, **kwargs):
            self.responses = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def parse(self, **kwargs):
            return response

    monkeypatch.setattr(runtime, "AsyncOpenAI", Client)
    report = await run_collection_graph(page, None, settings)
    assert report["extraction_status"] == {"code": expected}
    assert check(report, "표시 정보 추출")["status"] == "unavailable"
    assert report["score"] is None and report["verdict"] == "hold"


async def test_durable_reservation_denial_prevents_external_calls(page, settings, monkeypatch):
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    reservations = []
    settings.reserve_budget = lambda **kw: reservations.append(kw) or False
    model, _ = fake_model(monkeypatch, extraction())
    official = fake_official(monkeypatch)
    report = await run_collection_graph(page, "표시 제품", settings)
    assert not model and not official
    assert reservations == [
        {"seconds": 30.0, "tool_calls": 1},
        {"seconds": 15.0, "tool_calls": 1},
    ]
    assert check(report, "공식 등록 대조")["status"] == "unavailable"


async def test_local_call_limit_applies_without_budget_hook(page, settings, monkeypatch):
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    settings.max_tool_calls = 1
    model, _ = fake_model(monkeypatch, extraction())
    official = fake_official(monkeypatch)
    report = await run_collection_graph(page, None, settings)
    assert len(model) == 1 and not official
    assert check(report, "공식 등록 대조")["status"] == "unavailable"


async def test_saved_stage_is_reused_after_worker_recovery(page, settings, monkeypatch):
    settings.openai_api_key = "model-secret"
    snapshots = []
    settings.save_snapshot = lambda state: snapshots.append(state)
    calls, _ = fake_model(monkeypatch, extraction())
    expected = await run_collection_graph(page, None, settings)
    settings.graph_snapshot = snapshots[1]  # persisted extraction, before official node
    settings.save_snapshot = lambda state: None
    actual = await run_collection_graph(page, None, settings)
    assert len(calls) == 1
    assert actual == expected


async def test_previous_version_failed_snapshot_is_not_reused(page, settings, monkeypatch):
    settings.openai_api_key = "model-secret"
    snapshots = []
    settings.save_snapshot = lambda state: snapshots.append(state)
    fake_model(monkeypatch, error=RuntimeError("private provider detail"))
    await run_collection_graph(page, None, settings)
    stale = dict(snapshots[1])
    stale["version"] = 9
    settings.graph_snapshot = stale

    calls, _ = fake_model(monkeypatch, extraction())
    actual = await run_collection_graph(page, None, settings)
    assert len(calls) == 1
    assert actual["extraction_status"] == {"code": "extracted"}
    assert actual["product"]["name"] == "표시 제품"
    assert snapshots[-1]["version"] == 10


async def test_stale_snapshot_cannot_be_saved(page, settings):
    settings.save_snapshot = lambda state: False
    with pytest.raises(RuntimeError, match="no longer owns"):
        await run_collection_graph(page, None, settings)


async def test_checkpointer_state_does_not_leak_to_another_input(page, settings, monkeypatch):
    saver = InMemorySaver()
    settings.openai_api_key = "model-secret"
    calls, _ = fake_model(monkeypatch, extraction())
    first = await run_collection_graph(
        page, None, settings, checkpointer=saver, thread_id="same-thread"
    )
    assert first["product"]["name"] == "표시 제품"
    settings.openai_api_key = None
    page.text = "다른 페이지"
    second = await run_collection_graph(
        page, None, settings, checkpointer=saver, thread_id="same-thread"
    )
    assert second["product"]["name"] is None
    assert len(calls) == 1
    assert check(second, "표시 정보 추출")["status"] == "unavailable"


async def test_checkpointer_requires_explicit_thread(page, settings):
    with pytest.raises(ValueError, match="thread_id"):
        await run_collection_graph(page, None, settings, checkpointer=InMemorySaver())


async def test_official_transport_rejects_large_response(page, settings, monkeypatch):
    settings.food_safety_api_key = "official-secret"
    fake_official(monkeypatch, data=b"x" * (runtime.MAX_OFFICIAL_BYTES + 1))
    report = await run_collection_graph(page, "표시 제품", settings)
    assert check(report, "공식 등록 대조")["status"] == "unavailable"


async def test_numberless_match_requires_complete_unique_candidate_and_page_corroboration(page, settings, monkeypatch):
    page.text = "제품명: 표시 제품 제조사: 표시 제조사 비타민C 100 mg 1일 1정 항산화에 도움"
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    value = extraction()
    value.ingredients[0].basis = None
    fake_model(monkeypatch, value)
    fake_official(monkeypatch, [{
        "PRDLST_NM": "표시 제품", "BSSH_NM": "㈜표시 제조사", "PRDLST_REPORT_NO": "12345",
        "RAWMTRL_NM": "비타민C 100 mg", "LAST_UPDT_DTM": "20261101",
    }], total_count=1)
    report = await run_collection_graph(page, None, settings)
    assert check(report, "공식 등록 대조")["status"] == "verified"
    assert report["product"]["report_number"] is None
    assert report["official_match"]["state"] == "matched"
    assert report["official_match"]["queries"][0] == {
        "field": "PRDLST_NM", "value": "표시 제품", "total_count": 1,
        "returned_count": 1, "truncated": False,
    }
    assert "report_number" not in report["missing_fields"]


async def test_numberless_name_hit_is_candidate_if_query_total_missing_or_ingredient_conflicts(page, settings, monkeypatch):
    page.text = "제품명: 표시 제품 제조사: 표시 제조사 비타민C 100 mg 1일 1정 항산화에 도움"
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    value = extraction()
    value.ingredients[0].basis = None
    fake_model(monkeypatch, value)
    fake_official(monkeypatch, [{
        "PRDLST_NM": "표시 제품", "BSSH_NM": "표시 제조사", "PRDLST_REPORT_NO": "12345",
        "RAWMTRL_NM": "비타민C 100 mg", "OTHER": "10 mg",
    }], total_count=2)
    report = await run_collection_graph(page, None, settings)
    assert check(report, "공식 등록 대조")["status"] == "unverified"
    assert report["official_match"]["state"] == "candidate"
    assert report["official_match"]["queries"][0]["truncated"] is True
    assert report["official_match"]["evidence"][-1]["outcome"] == "match"

    fake_official(monkeypatch, [{
        "PRDLST_NM": "표시 제품", "BSSH_NM": "표시 제조사", "PRDLST_REPORT_NO": "12345",
        "RAWMTRL_NM": "비타민C 10 mg",
    }], total_count=1)
    conflict = await run_collection_graph(page, None, settings)
    assert check(conflict, "공식 등록 대조")["status"] == "unverified"
    assert conflict["official_match"]["evidence"][-1]["outcome"] == "conflict"

    fake_official(monkeypatch, [{
        "PRDLST_NM": "표시 제품", "BSSH_NM": "표시 제조사", "PRDLST_REPORT_NO": "12345",
        "RAWMTRL_NM": "비타민C", "OTHER_FIELD": "100 mg",
    }], total_count=1)
    separated = await run_collection_graph(page, None, settings)
    assert check(separated, "공식 등록 대조")["status"] == "unverified"
    assert separated["official_match"]["evidence"][-1]["outcome"] == "missing"


async def test_exact_two_auxiliary_ingredients_separate_everytime_shot_from_strong(page, settings, monkeypatch):
    page.text = "제품명: 에브리타임 샷 제조사: 한국인삼공사 프로폴리스(호주), 글루콘산아연, 치커리뿌리추출물(벨기에)"
    page.html = "<p>제품명: 에브리타임 샷</p><p>제조원: 한국인삼공사</p><p>프로폴리스 글루콘산아연 치커리뿌리추출물</p>"
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    model_value = runtime.Extraction.model_validate({
        "product_name": {"value": "에브리타임 샷", "excerpt": "제품명: 에브리타임 샷"},
        "manufacturer": {"value": "한국인삼공사", "excerpt": "제조사: 한국인삼공사"},
        "report_number": None, "claims": [],
        "ingredients": [
            {"name": "프로폴리스", "amount": None, "unit": None, "basis": None, "excerpt": "프로폴리스(호주)"},
            {"name": "글루콘산아연", "amount": None, "unit": None, "basis": None, "excerpt": "글루콘산아연"},
            {"name": "치커리뿌리추출물", "amount": None, "unit": None, "basis": None, "excerpt": "치커리뿌리추출물(벨기에)"},
        ],
    })
    fake_model(monkeypatch, model_value)
    fake_official(monkeypatch, [
        {"PRDLST_NM": "에브리타임샷", "BSSH_NM": "(주)한국인삼공사", "PRDLST_REPORT_NO": "20150002152119",
         "ETC_RAWMTRL_NM": "프로폴리스, 글루콘산아연, 치커리뿌리추출물, 프락토올리고당"},
        {"PRDLST_NM": "에브리타임샷스트롱", "BSSH_NM": "(주)한국인삼공사", "PRDLST_REPORT_NO": "20040020013449",
         "ETC_RAWMTRL_NM": "정제수, 용설란시럽, 프락토올리고당, 생강시럽농축액, 계피농축액"},
    ], total_count=2)
    report = await run_collection_graph(page, None, settings)
    assert check(report, "공식 등록 대조")["status"] == "verified"
    assert report["product"]["name"] == "에브리타임 샷"
    assert report["product"]["report_number"] is None
    assert report["official_match"]["matched_record"]["PRDLST_REPORT_NO"] == "20150002152119"
    assert len(report["official_match"]["candidates"]) == 2
    matched_ingredients = [item for item in report["official_match"]["evidence"] if item["field"] == "additional_ingredient"]
    assert len(matched_ingredients) == 3
    assert all(item["outcome"] == "match" for item in matched_ingredients)


@pytest.mark.parametrize("total_count", [0, 2, 1.0, True, "1.0", "-1"])
async def test_inconsistent_or_invalid_total_count_never_completes_candidate_set(page, settings, monkeypatch, total_count):
    page.text = "제품명: 표시 제품 제조사: 표시 제조사 비타민C 100 mg"
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    value = extraction()
    value.report_number = None
    value.ingredients[0].basis = None
    fake_model(monkeypatch, value)
    fake_official(monkeypatch, [{
        "PRDLST_NM": "표시 제품", "BSSH_NM": "표시 제조사", "PRDLST_REPORT_NO": "12345",
        "RAWMTRL_NM": "비타민C 100 mg",
    }], total_count=total_count)
    report = await run_collection_graph(page, None, settings)
    assert check(report, "공식 등록 대조")["status"] == "unverified"
    assert report["official_match"]["state"] == "candidate"
    assert report["official_match"]["queries"][0]["truncated"] is True


def test_ingredient_name_comparison_does_not_accept_substrings():
    extracted = {"ingredients": [{"name": "아연", "amount": None, "unit": None, "basis": None}]}
    record = {"ETC_RAWMTRL_NM": "글루콘산아연", "RAWMTRL_NM": "홍삼"}
    assert runtime._additional_evidence(extracted, record) is False
    assert runtime._ingredient_name_key("홍삼(발효)") != runtime._ingredient_name_key("홍삼")
    assert runtime._product_identity_normalized("A-B") != runtime._product_identity_normalized("AB")
    assert runtime._additional_evidence(
        {"ingredients": [{"name": "정제수", "amount": None, "unit": None}]},
        {"ETC_RAWMTRL_NM": "정제수, 홍삼", "RAWMTRL_NM": "홍삼"},
    ) is False


def test_ingredient_amount_comparison_keeps_units_and_bases_together():
    page_ingredient = {"name": "아연", "amount": "10", "unit": "g", "basis": None}
    assert runtime._additional_evidence(
        {"ingredients": [page_ingredient]}, {"RAWMTRL_NM": "아연 10 mg"}
    ) is False
    page_ingredient["unit"] = "mg"
    assert runtime._additional_evidence(
        {"ingredients": [page_ingredient]}, {"RAWMTRL_NM": "아연 10mg"}
    ) is True
    page_ingredient["basis"] = "1일 1정"
    assert runtime._additional_evidence(
        {"ingredients": [page_ingredient]}, {"RAWMTRL_NM": "아연 10 mg"}
    ) is False


async def test_numbered_registration_can_confirm_grounded_major_ingredients_with_name_difference(page, settings, monkeypatch):
    page.text = "판매명: ER Hana 제조사: 표시 제조사 신고번호: 2024-17 비타민 D 루바브뿌리추출물(ERr731®)(제2024-17호) 비타민K"
    settings.openai_api_key = "model-secret"
    settings.food_safety_api_key = "official-secret"
    model_value = runtime.Extraction.model_validate({
        "product_name": {"value": "ER Hana", "excerpt": "판매명: ER Hana"},
        "manufacturer": {"value": "표시 제조사", "excerpt": "제조사: 표시 제조사"},
        "report_number": {"value": "2024-17", "excerpt": "신고번호: 2024-17"},
        "claims": [], "ingredients": [
            {"name": "비타민 D", "amount": "10", "unit": "㎍", "basis": None, "excerpt": "비타민 D"},
            {"name": "루바브뿌리추출물(ERr731®)(제2024-17호)", "amount": None, "unit": None, "basis": None, "excerpt": "루바브뿌리추출물(ERr731®)(제2024-17호)"},
            {"name": "비타민K", "amount": "70", "unit": "㎍", "basis": None, "excerpt": "비타민K"},
        ],
    })
    fake_model(monkeypatch, model_value)
    record = {"PRDLST_NM": "공식 루바브 밸런스", "BSSH_NM": "표시 제조사", "PRDLST_REPORT_NO": "2024-17",
              "RAWMTRL_NM": "비타민 D, 루바브뿌리추출물(ERr731Ⓡ)(제2024-17호), 비타민K", "STDR_STND": "비타민D 10㎍/0.08g, Rhaponticin 2.52mg/0.08g, 비타민K 70㎍/0.08g",
              "LAST_UPDT_DTM": "20261110"}
    fake_official(monkeypatch, [record], total_count=1)
    report = await run_collection_graph(page, None, settings)
    assert report["product"]["name"] == "ER Hana"
    assert report["official_match"]["state"] == "matched"
    assert report["official_match"]["reasons"] == ["registration_identity_with_name_difference"]
    assert report["official_match"]["name_difference"] == {"page_name": "ER Hana", "official_name": "공식 루바브 밸런스"}
    assert report["official_match"]["evidence"][0]["outcome"] == "conflict"
    assert next(item for item in report["official_match"]["evidence"] if item["field"] == "report_number")["outcome"] == "match"
    assert report["official_match"]["matched_record"] == record
    assert any(item["field"] == "dosage_form" and item["outcome"] == "missing" for item in report["official_match"]["evidence"])
    assert check(report, "공식 등록 대조")["detail"] == "공식 등록정보 대조 확인 — 판매명 차이 있음"


def test_registered_major_ingredient_gate_requires_every_exact_name_and_blocks_minor_auxiliary_only():
    extracted = {"ingredients": [{"name": "비타민 D"}, {"name": "루바브뿌리추출물(ERr731®)(제2024-17호)"}, {"name": "비타민K"}]}
    record = {"RAWMTRL_NM": "비타민 D,루바브뿌리추출물(ERr731Ⓡ)(제2024-17호),비타민K"}
    ok, evidence = runtime._registration_major_evidence(extracted, record, ["product-page"])
    assert ok is True
    assert all(row["outcome"] == "match" for row in evidence if row["field"] == "major_ingredient")
    missing, evidence = runtime._registration_major_evidence({"ingredients": [{"name": "프로폴리스"}, {"name": "글루콘산아연"}]},
                                                              {"RAWMTRL_NM": "비타민 D,루바브뿌리추출물(ERr731Ⓡ),비타민K", "ETC_RAWMTRL_NM": "프로폴리스,글루콘산아연"}, [])
    assert missing is False
    assert sum(row["outcome"] == "match" for row in evidence if row["field"] == "major_ingredient") == 0
    variant, _ = runtime._registration_major_evidence({"ingredients": [{"name": "비타민 D3"}]}, {"RAWMTRL_NM": "비타민 D"}, [])
    assert variant is False


def test_registered_amount_requires_same_explicit_basis_and_preserves_conflict():
    row = {"STDR_STND": "비타민D 표시량(10㎍/1정)"}
    page = {"name": "비타민D", "amount": "20", "unit": "㎍", "basis": "1정"}
    conflict = runtime._registered_amount_evidence(page, row, ["product-page"], "official-row")
    assert conflict["outcome"] == "conflict"
    assert conflict["official_value"] == "비타민D 표시량(10㎍/1정)"
    page["basis"] = None
    assert runtime._registered_amount_evidence(page, row, [], "official-row")["outcome"] == "missing"
    page["basis"] = "0.08g"
    assert runtime._registered_amount_evidence(page, row, [], "official-row")["outcome"] == "missing"
