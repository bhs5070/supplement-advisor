"""Independent adversarial checks for direct product-information table extraction."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from supplement_advisor.agents import collection_graph as runtime
from supplement_advisor.agents import run_collection_graph
from supplement_advisor.agents.structured_extraction import extract_product_table
from supplement_advisor.collection import CollectedPage

PRODUCT_HTML = """
<table>
  <tr><th colspan="2">브랜드 밸런스 상품정보</th></tr>
  <tr><th>제품명</th><td>브랜드 밸런스</td></tr>
  <tr><th>제조업소</th><td>㈜서흥</td></tr>
  <tr><th>품목제조신고번호</th><td>200400200062002</td></tr>
  <tr><th>기능정보</th><td>[홍삼농축액 (제 2004-23호)]</td></tr>
</table>
<footer>
  <table>
    <tr><th colspan="2">판매자 정보</th></tr>
    <tr><th>판매업소</th><td>온라인판매사</td></tr>
    <tr><th>사업자등록번호</th><td>123-45-67890</td></tr>
  </table>
</footer>
"""

PRODUCT_TEXT = (
    "브랜드 밸런스 상품정보 제품명 브랜드 밸런스 제조업소 ㈜서흥 "
    "품목제조신고번호 200400200062002 기능정보 홍삼농축액 (제 2004-23호) "
    "판매자 정보 판매업소 온라인판매사 사업자등록번호 123-45-67890"
)


def _page(html=PRODUCT_HTML, text=PRODUCT_TEXT):
    return CollectedPage(
        url="https://shop.example/product?private=secret",
        title="브랜드 밸런스",
        text=text,
        html=html,
        image_urls=[],
    )


def _table(title, rows):
    row_html = "".join(f"<tr><th>{label}</th><td>{value}</td></tr>" for label, value in rows)
    return f"<table><tr><th colspan='2'>{title}</th></tr>{row_html}</table>"


async def test_literal_table_path_reports_direct_extraction_without_model_or_budget(monkeypatch):
    page = _page()
    saved = []
    settings = SimpleNamespace(
        openai_api_key="configured-but-not-needed",
        openai_model="gpt-5.6-luna",
        food_safety_api_key=None,
        external_timeout_seconds=15,
        model_timeout_seconds=30,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
        save_snapshot=lambda snapshot: saved.append(snapshot),
        reserve_budget=lambda **kwargs: pytest.fail("literal extraction must not reserve an LLM call"),
    )

    class UnexpectedModel:
        def __init__(self, **kwargs):
            pytest.fail("literal extraction must not call the model")

    monkeypatch.setattr(runtime, "AsyncOpenAI", UnexpectedModel)
    report = await run_collection_graph(page, None, settings)

    assert report["extraction_status"] == {"code": "structured_page"}
    assert report["product"]["name"] == "브랜드 밸런스"
    assert report["product"]["manufacturer"] == "㈜서흥"
    assert report["product"]["report_number"] == "200400200062002"
    assert report["ingredients"] == [
        {
            "name": "홍삼농축액 (제 2004-23호)",
            "amount": None,
            "unit": None,
            "basis": None,
        }
    ]
    extraction_check = next(item for item in report["checks"] if item["name"] == "표시 정보 추출")
    assert extraction_check["status"] == "unverified"
    assert "직접 읽었습니다" in extraction_check["detail"]
    assert "AI" not in extraction_check["detail"] and "모델이 추출" not in extraction_check["detail"]
    assert report["score"] is None and report["verdict"] == "hold"
    assert saved and all(item["version"] == 10 for item in saved)


async def test_official_lookup_uses_only_the_literal_page_number(monkeypatch):
    page = _page()
    queries = []
    row = {
        "PRDLST_NM": "브랜드 밸런스 공식 등록명",
        "BSSH_NM": "㈜서흥",
        "PRDLST_REPORT_NO": "200400200062002",
        "RAWMTRL_NM": "홍삼농축액 (제 2004-23호)",
        "LAST_UPDT_DTM": "20261110",
    }

    async def records(value, key, timeout, *, report_number=None):
        queries.append((value, key, timeout, report_number))
        return [row], 1

    monkeypatch.setattr(runtime, "_official_records", records)
    settings = SimpleNamespace(
        openai_api_key="configured-but-not-needed",
        openai_model="gpt-5.6-luna",
        food_safety_api_key="fixture-key",
        external_timeout_seconds=15,
        model_timeout_seconds=30,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
        reserve_budget=lambda **kwargs: True,
    )

    class UnexpectedModel:
        def __init__(self, **kwargs):
            pytest.fail("the direct table result must be used before any LLM call")

    monkeypatch.setattr(runtime, "AsyncOpenAI", UnexpectedModel)
    report = await run_collection_graph(page, None, settings)

    assert queries == [("200400200062002", "fixture-key", 15.0, "200400200062002")]
    assert report["product"]["report_number"] == "200400200062002"
    assert report["official_match"]["state"] == "matched", report["checks"]
    assert report["product"]["name"] == "브랜드 밸런스"
    assert report["official_match"]["matched_record"]["PRDLST_REPORT_NO"] == "200400200062002"
    assert report["official_match"]["name_difference"] == {
        "page_name": "브랜드 밸런스",
        "official_name": "브랜드 밸런스 공식 등록명",
    }
    assert report["sources"][0]["kind"] == "advertising"
    assert report["sources"][1]["kind"] == "official"


async def test_different_functional_registration_code_stays_candidate(monkeypatch):
    page = _page()
    row = {
        "PRDLST_NM": "브랜드 밸런스 공식 등록명",
        "BSSH_NM": "㈜서흥",
        "PRDLST_REPORT_NO": "200400200062002",
        "RAWMTRL_NM": "홍삼농축액 (제 2004-99호)",
        "LAST_UPDT_DTM": "20261110",
    }

    async def records(value, key, timeout, *, report_number=None):
        return [row], 1

    monkeypatch.setattr(runtime, "_official_records", records)
    settings = SimpleNamespace(
        openai_api_key="configured-but-not-needed",
        openai_model="gpt-5.6-luna",
        food_safety_api_key="fixture-key",
        external_timeout_seconds=15,
        model_timeout_seconds=30,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
        reserve_budget=lambda **kwargs: True,
    )

    class UnexpectedModel:
        def __init__(self, **kwargs):
            pytest.fail("the direct table result must be used before any LLM call")

    monkeypatch.setattr(runtime, "AsyncOpenAI", UnexpectedModel)
    report = await run_collection_graph(page, None, settings)

    assert report["product"]["name"] == "브랜드 밸런스"
    assert report["ingredients"][0]["name"] == "홍삼농축액 (제 2004-23호)"
    assert report["official_match"]["state"] == "candidate"
    assert report["official_match"]["reasons"] == ["registration_identity_evidence_incomplete"]
    major = next(
        item for item in report["official_match"]["evidence"]
        if item["field"] == "major_ingredient"
    )
    assert major["outcome"] == "missing"


def test_functional_ingredient_registration_qualifier_is_preserved_verbatim():
    extracted = extract_product_table(PRODUCT_HTML)
    assert extracted is not None
    assert extracted["ingredients"] == [
        {
            "name": "홍삼농축액 (제 2004-23호)",
            "amount": None,
            "unit": None,
            "basis": None,
            "excerpt": "홍삼농축액 (제 2004-23호)",
        }
    ]


def test_saved_real_seller_page_html_extracts_only_literal_identity_and_ingredients():
    source = Path(__file__).parents[1] / "work/verification/2026-11-10-independent-seller-source.html"
    if not source.exists():
        pytest.skip("real seller-page capture is a local verification artifact")

    extracted = extract_product_table(source.read_text(encoding="utf-8", errors="replace"))
    assert extracted is not None
    assert extracted["product_name"]["value"] == "이알하나 (ER Hana®)"
    assert extracted["manufacturer"]["value"] == "(주)서흥"
    assert extracted["report_number"]["value"] == "200400200062002"
    assert [item["name"] for item in extracted["ingredients"]] == [
        "루바브뿌리추출물(ERr731®)(제2024-17호)",
        "비타민D",
        "비타민K",
    ]


def test_seller_and_business_registration_numbers_do_not_fill_manufacturer_or_product_number():
    html = _table(
        "브랜드 밸런스 상품정보",
        [
            ("제품명", "브랜드 밸런스"),
            ("판매업소", "온라인판매사"),
            ("사업자등록번호", "1234567890"),
            ("기능정보", "[홍삼농축액]"),
        ],
    )
    assert extract_product_table(html) is None


def test_distinct_report_numbers_in_same_table_are_ambiguous():
    html = _table(
        "브랜드 밸런스 상품정보",
        [
            ("제품명", "브랜드 밸런스"),
            ("제조업소", "㈜서흥"),
            ("품목제조신고번호", "200400200062002"),
            ("품목제조신고번호", "200400200062003"),
            ("기능정보", "[홍삼농축액]"),
        ],
    )
    assert extract_product_table(html) is None


def test_malformed_table_does_not_create_literal_identity():
    html = (
        "<table><tr><th colspan='2'>브랜드 밸런스 상품정보</th></tr>"
        "<tr><th>제품명<td>브랜드 밸런스</tr>"
        "<tr><th>제조업소</th><td>㈜서흥</td></tr>"
        "<tr><th>품목제조신고번호</th><td>200400200062002</td></tr>"
        "<tr><th>기능정보</th><td>[홍삼농축액]</td></tr>"
    )
    assert extract_product_table(html) is None


def test_related_product_table_does_not_contribute_ingredients():
    primary = _table(
        "브랜드 밸런스 상품정보",
        [
            ("제품명", "브랜드 밸런스"),
            ("제조업소", "㈜서흥"),
            ("품목제조신고번호", "200400200062002"),
            ("기능정보", "[홍삼농축액]"),
        ],
    )
    related = _table(
        "브랜드 밸런스 플러스 상품정보",
        [("기능정보", "[밀크씨슬추출물]")],
    )
    extracted = extract_product_table(primary + related)
    assert extracted is not None
    assert [item["name"] for item in extracted["ingredients"]] == ["홍삼농축액"]


def test_footer_identity_fields_cannot_complete_an_incomplete_product_table():
    product = _table(
        "브랜드 밸런스 상품정보",
        [("제품명", "브랜드 밸런스"), ("기능정보", "[홍삼농축액]")],
    )
    footer = _table(
        "브랜드 고객센터 정보",
        [
            ("제조업소", "㈜서흥"),
            ("품목제조신고번호", "200400200062002"),
        ],
    )
    assert extract_product_table(product + footer) is None
