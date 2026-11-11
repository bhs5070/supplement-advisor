"""Independent regressions for numbered registration name differences."""

import re
from types import SimpleNamespace

import pytest

from supplement_advisor.agents import collection_graph as runtime
from supplement_advisor.collection import CollectedPage


def _numbered_record(**overrides):
    row = {
        "PRDLST_NM": "공식 루바브 밸런스",
        "BSSH_NM": "표시 제조사",
        "PRDLST_REPORT_NO": "2024-17",
        "RAWMTRL_NM": "비타민 D, 루바브뿌리추출물(ERr731Ⓡ)(제2024-17호), 비타민 K",
        "ETC_RAWMTRL_NM": "프로폴리스, 글루콘산아연",
        "PRDT_SHAP_CD_NM": "정",
        "STDR_STND": "비타민D : 표시량(10㎍/1정)의 80%~180%",
    }
    row.update(overrides)
    return row


def _extraction(**overrides):
    value = {
        "product_name": "ER Hana",
        "manufacturer": "표시 제조사",
        "report_number": "2024-17",
        "ingredients": [
            {"name": "비타민 D", "amount": None, "unit": None, "basis": None},
            {"name": "루바브뿌리추출물(ERr731®)(제2024-17호)", "amount": None, "unit": None, "basis": None},
            {"name": "비타민 K", "amount": None, "unit": None, "basis": None},
        ],
    }
    value.update(overrides)
    return value


async def _check(monkeypatch, extraction, rows, total=None):
    async def official_records(value, key, timeout, *, report_number=None):
        assert report_number == extraction["report_number"]
        return rows, len(rows) if total is None else total

    monkeypatch.setattr(runtime, "_official_records", official_records)
    settings = SimpleNamespace(
        food_safety_api_key="configured",
        external_timeout_seconds=15,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
    )
    budget = runtime._CallBudget(settings)
    return await runtime._check_official({"extraction": extraction}, None, settings, budget)


@pytest.mark.asyncio
async def test_registered_major_ingredients_all_required_even_when_auxiliary_ingredients_match(monkeypatch):
    row = _numbered_record(RAWMTRL_NM="비타민 D, 루바브뿌리추출물(ERr731Ⓡ)(제2024-17호), 비타민 K")
    extraction = _extraction(ingredients=[
        {"name": "프로폴리스", "amount": None, "unit": None, "basis": None},
        {"name": "글루콘산아연", "amount": None, "unit": None, "basis": None},
    ])
    result = await _check(monkeypatch, extraction, [row])
    match = result["official_match"]
    assert match["state"] == "candidate"
    assert match["matched_record"] is None
    major_rows = [item for item in match["evidence"] if item["field"] == "major_ingredient"]
    assert len(major_rows) == 3 and all(item["outcome"] == "missing" for item in major_rows)
    assert "registration_identity_with_name_difference" not in match["reasons"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"BSSH_NM": "다른 제조사"},
        {"PRDLST_REPORT_NO": "다른 번호"},
    ],
)
async def test_number_or_manufacturer_conflict_cannot_become_name_difference_match(monkeypatch, overrides):
    row = _numbered_record(**overrides)
    result = await _check(monkeypatch, _extraction(), [row])
    assert result["official_match"]["state"] == "candidate"
    assert result["official_match"]["matched_record"] is None
    assert "registration_identity_with_name_difference" not in result["official_match"]["reasons"]


@pytest.mark.asyncio
async def test_supported_name_difference_match_keeps_page_and_official_names_and_provenance(monkeypatch):
    row = _numbered_record()
    extraction = _extraction()
    result = await _check(monkeypatch, extraction, [row])
    match = result["official_match"]
    assert match["state"] == "matched"
    assert match["reasons"] == ["registration_identity_with_name_difference"]
    assert match["name_difference"] == {
        "page_name": "ER Hana",
        "official_name": "공식 루바브 밸런스",
    }
    assert match["matched_record"] == row
    assert any(
        item["field"] == "product_name"
        and item["page_value"] == "ER Hana"
        and item["official_value"] == "공식 루바브 밸런스"
        and item["outcome"] == "conflict"
        for item in match["evidence"]
    )
    official_source = next(
        item["source_ids"][1]
        for item in match["evidence"]
        if item["field"] == "report_number"
    )
    assert official_source.startswith("official-i0030-2024-17-")


@pytest.mark.asyncio
async def test_duplicate_or_truncated_number_results_remain_candidates(monkeypatch):
    row = _numbered_record()
    duplicate = {**row, "PRDLST_NM": "다른 공식 기록"}
    duplicate_result = await _check(monkeypatch, _extraction(), [row, duplicate])
    assert duplicate_result["official_match"]["state"] == "candidate"
    assert duplicate_result["official_match"]["matched_record"] is None

    truncated_result = await _check(monkeypatch, _extraction(), [row], total=2)
    assert truncated_result["official_match"]["state"] == "candidate"
    assert truncated_result["official_match"]["matched_record"] is None
    assert truncated_result["official_match"]["queries"][0]["truncated"] is True


@pytest.mark.parametrize(
    "page_item, expected",
    [
        ({"name": "비타민 D", "amount": "20", "unit": "㎍", "basis": "1정"}, "conflict"),
        ({"name": "비타민 D", "amount": "20", "unit": "㎍", "basis": None}, "missing"),
        ({"name": "비타민 D", "amount": "20", "unit": "㎍", "basis": "0.08g"}, "missing"),
    ],
)
def test_registered_amount_basis_suffix_cannot_hide_conflict(page_item, expected):
    evidence = runtime._registered_amount_evidence(
        page_item,
        {"STDR_STND": "비타민D 표시량(10㎍/1정)"},
        ["product-page"],
        "official-row",
    )
    assert evidence["outcome"] == expected
    assert evidence["source_ids"] == ["product-page", "official-row"]


def test_registered_percent_range_keeps_the_basis_inside_the_declared_amount():
    evidence = runtime._registered_amount_evidence(
        {"name": "비타민D", "amount": "20", "unit": "㎍", "basis": "0.08g"},
        {"STDR_STND": "비타민D : 표시량(10 ㎍/0.08g)의 80%~180%"},
        ["product-page"],
        "official-row",
    )
    assert evidence["outcome"] == "conflict"


def test_every_same_name_page_ingredient_is_checked_for_a_comparable_conflict():
    extracted = {"ingredients": [
        {"name": "비타민 D", "amount": None, "unit": None, "basis": None},
        {"name": "비타민 D", "amount": "20", "unit": "㎍", "basis": "1정"},
    ]}
    ok, evidence = runtime._registration_major_evidence(
        extracted,
        _numbered_record(STDR_STND="비타민D 표시량(10㎍/1정)"),
        ["product-page"],
    )
    assert ok is False
    assert any(item["field"] == "ingredient_amount" and item["outcome"] == "conflict" for item in evidence)


def test_registration_gate_does_not_hide_conflict_in_later_same_name_ingredient():
    extracted = {"ingredients": [
        {"name": "비타민 D", "amount": None, "unit": None, "basis": None},
        {"name": "비타민 D", "amount": "20", "unit": "㎍", "basis": "1정"},
        {"name": "루바브뿌리추출물(ERr731®)(제2024-17호)", "amount": None, "unit": None, "basis": None},
        {"name": "비타민 K", "amount": None, "unit": None, "basis": None},
    ]}
    ok, evidence = runtime._registration_major_evidence(
        extracted,
        _numbered_record(STDR_STND="비타민D 표시량(10㎍/1정)"),
        ["product-page"],
    )
    assert ok is False
    assert any(item["field"] == "ingredient_amount" and item["outcome"] == "conflict" for item in evidence)


def test_amounts_with_different_units_are_not_converted_or_called_conflicts():
    evidence = runtime._registered_amount_evidence(
        {"name": "비타민 D", "amount": "0.01", "unit": "mg", "basis": "1정"},
        {"STDR_STND": "비타민D 표시량(10㎍/1정)"},
        ["product-page"],
        "official-row",
    )
    assert evidence["outcome"] == "missing"


def test_experimental_reasoning_does_not_supply_success_reason_to_candidate():
    # Candidate explanations stay tied to their actual incomplete identity evidence.
    dto = runtime._match("candidate", "registration_identity_evidence_incomplete")
    assert dto["state"] == "candidate"
    assert dto["reasons"] == ["registration_identity_evidence_incomplete"]
    assert not re.search(r"확인(?:됨|했습니다)|일치(?:함|합니다)", dto["reason"])


@pytest.mark.asyncio
async def test_extraction_prompt_expands_table_coverage_without_changing_schema_or_call_limits(monkeypatch):
    captured = []
    parsed = runtime.Extraction.model_validate({
        "product_name": None,
        "manufacturer": None,
        "report_number": None,
        "claims": [],
        "ingredients": [],
    })

    class MockClient:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            assert kwargs["timeout"] == 15

        async def __aenter__(self):
            self.responses = self
            return self

        async def __aexit__(self, *args):
            return None

        async def parse(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(output_parsed=parsed)

    monkeypatch.setattr(runtime, "AsyncOpenAI", MockClient)
    settings = SimpleNamespace(
        openai_api_key="configured",
        openai_model="gpt-5.6-luna",
        external_timeout_seconds=15,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
    )
    page = CollectedPage(
        url="https://example.org/product",
        title="ER Hana",
        text="원재료 및 영양·기능정보",
        html="",
        image_urls=[],
    )
    result = await runtime._extract(page, settings, runtime._CallBudget(settings))
    assert result["extraction_code"] == "extracted"
    assert set(runtime.Extraction.model_fields) == {
        "product_name", "manufacturer", "report_number", "claims", "ingredients"
    }
    request = captured[0]
    assert request["model"] == "gpt-5.6-luna"
    assert request["reasoning"] == {"effort": "none"}
    assert request["max_output_tokens"] == 4_000
    system_prompt = request["input"][0]["content"]
    assert "원재료 목록뿐 아니라 영양·기능정보 표" in system_prompt
    assert "기능성 성분명·함량·단위·섭취 기준도 각각 추출" in system_prompt
    assert "원산지 표시" in system_prompt and "basis에는 섭취 기준만" in system_prompt
    assert "상표명과 기능성 등록 코드는 성분명에 보존" in system_prompt
    assert "함량·단위 변환" in system_prompt and "추정은 금지" in system_prompt
