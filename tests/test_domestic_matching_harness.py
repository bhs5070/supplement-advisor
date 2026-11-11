"""Offline tests for the domestic matching sample harness."""

from types import SimpleNamespace

import pytest

from scripts import verify_domestic_matching as domestic


def _report(extraction_status="unverified", official_status="unverified"):
    return {
        "product": {"name": "제품", "manufacturer": "제조사", "report_number": None},
        "sources": [],
        "checks": [
            {"name": "표시 정보 추출", "status": extraction_status},
            {"name": "공식 등록 대조", "status": official_status},
        ],
    }


def test_safe_source_url_preserves_path_but_drops_private_url_components():
    assert domestic._safe_url(
        "https://user:secret@shop.example/p?token=hidden#fragment"
    ) == "https://shop.example/p"


def test_public_product_id_is_recorded_without_other_query_values():
    assert domestic._public_product_id(
        "https://shop.example/p?itemId=public-123&token=secret"
    ) == "public-123"


def test_identity_observation_requires_page_text_and_separates_number_marker():
    product = {
        "submitted_name": "락토핏 골드",
        "expected_manufacturer_hint": "종근당건강",
    }
    observed = domestic._identity_observed(
        "제품 락토핏 골드, 제조원 종근당건강㈜", product
    )
    assert observed == {
        "product_name_hint": True,
        "manufacturer_hint": True,
        "report_number_marker": False,
    }


def test_identity_hint_allows_brand_and_product_name_as_separate_page_tokens():
    product = {
        "submitted_name": "정관장 에브리타임 샷",
        "expected_manufacturer_hint": "한국인삼공사",
    }
    observed = domestic._identity_observed(
        "정관장 브랜드 제품 소개 에브리타임 샷 제조원 한국인삼공사", product
    )
    assert observed["product_name_hint"] is True
    assert observed["manufacturer_hint"] is True


def test_cli_requires_explicit_opt_in_for_live_external_calls():
    assert domestic.parse_args([]).use_configured_keys is False


@pytest.mark.asyncio
async def test_sample_keeps_failed_and_insufficient_products_in_denominators(monkeypatch):
    settings = SimpleNamespace(
        openai_api_key="configured",
        food_safety_api_key="configured",
        model_copy=lambda update: SimpleNamespace(
            openai_api_key=None, food_safety_api_key=None
        ),
    )
    monkeypatch.setattr(domestic, "get_settings", lambda: settings)
    pages = [
        SimpleNamespace(
            title="Page one",
            text=f'{product["submitted_name"]} 제조원 {product["expected_manufacturer_hint"]}',
        )
        for product in domestic.PRODUCTS
    ]
    pages[2].text = "정관장"
    collection_calls = 0

    async def collect(_url):
        nonlocal collection_calls
        current = collection_calls
        collection_calls += 1
        if current == 1:
            raise RuntimeError("private detail must not leak")
        return pages[current]

    graph_calls = 0

    async def graph(_page, _name, _settings):
        nonlocal graph_calls
        graph_calls += 1
        return _report()

    monkeypatch.setattr(domestic, "collect_page", collect)
    monkeypatch.setattr(domestic, "run_collection_graph", graph)
    result = await domestic.sample(use_configured_keys=True)

    assert graph_calls == 1
    assert result["denominators"] == {
        "products_attempted_this_run": 3,
        "collection_success": 2,
        "identity_page_text_eligible_for_extraction": 1,
        "complete_extracted_identity_name_manufacturer_number": 0,
        "model_call_attempted": 1,
        "model_call_completed": 1,
        "official_check_non_unavailable": 1,
        "official_verified": 0,
    }
    assert result["products"][1]["collection_error"] == "RuntimeError"
    assert result["products"][2]["extraction_status"] == (
        "not_attempted_insufficient_page_text"
    )
    assert result["control_categories_not_mixed_into_live_sample"] == list(
        domestic.CONTROL_CATEGORIES
    )


def test_merge_provenance_replaces_only_the_matching_product_row():
    prior = {
        "denominators": {"model_call_attempted": 1, "model_call_completed": 1},
        "products": [
            {
                "source_url": "https://shop.example/p?id=1560&tracking=private",
                "collection_status": "success",
                "identity_information_sufficient_for_extraction": True,
            },
            {"source_product_id": "CHC0000284", "collection_status": "success"},
        ],
    }
    latest = {
        "denominators": {"model_call_attempted": 1, "model_call_completed": 1},
        "products": [
            {
                "source_product_id": "1560",
                "collection_status": "success",
                "identity_page_text_eligible_for_extraction": True,
                "extracted_identity": {
                    "name": "에브리타임 샷",
                    "manufacturer": "한국인삼공사",
                    "report_number": None,
                },
                "official_match_status": "unverified",
                "official_check_non_unavailable": True,
            }
        ],
    }
    merged = domestic.merge_evidence(
        prior, latest, prior_file="first.json", latest_file="kgc.json"
    )
    assert len(merged["products"]) == 2
    assert merged["products"][-1]["identity_page_text_eligible_for_extraction"] is True
    assert merged["denominators"]["model_call_attempted"] == 2
    assert merged["denominators"]["official_check_non_unavailable"] == 1
    assert merged["merge_provenance"]["separate_runs"] is True
