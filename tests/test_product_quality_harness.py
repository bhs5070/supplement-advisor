"""Tests for the small live-page report quality harness."""

from types import SimpleNamespace

import pytest

from scripts import verify_product_quality as quality


def valid_report():
    return {
        "scope": "collection_only",
        "summary": "Collection only",
        "product": {"name": None, "manufacturer": None},
        "claims": [],
        "score": None,
        "verdict": "hold",
        "missing_fields": ["ingredient_label"],
        "limitations": ["No quality guarantee"],
        "sources": [{"id": "product-page", "url": "https://example.com/product"}],
        "checks": [
            {"name": "페이지 수집", "status": "verified", "source_ids": ["product-page"]},
            {"name": "표시 정보 추출", "status": "unavailable", "source_ids": []},
            {"name": "공식 등록 대조", "status": "unavailable", "source_ids": []},
            {"name": "개인 적합성", "status": "not_applicable", "source_ids": []},
        ],
        "ingredients": [
            {"name": "Vitamin C", "amount": None, "unit": None, "basis": None}
        ],
    }


def test_inspect_report_accepts_grounded_collection_only_contract():
    assert quality.inspect_report(valid_report()) == []


def test_inspect_report_flags_scope_score_hold_source_and_check_errors():
    report = valid_report()
    report.update({"scope": "full_review", "score": 3, "verdict": "recommend"})
    report["checks"][0]["status"] = "success"
    report["checks"][0]["source_ids"] = ["missing"]
    report["ingredients"][0].pop("amount")
    report["sources"] = []
    issues = quality.inspect_report(report)
    assert "scope_not_collection_only" in issues
    assert "score_should_be_null" in issues
    assert "verdict_should_be_hold" in issues
    assert "source_missing" in issues
    assert "check_0_invalid_status" in issues
    assert "check_0_dangling_source" in issues
    assert "ingredient_amount_field_missing" in issues


def test_configured_credentials_are_ignored_by_default(monkeypatch):
    class FakeSettings(SimpleNamespace):
        def model_copy(self, *, update):
            return SimpleNamespace(**{**vars(self), **update})

    original = FakeSettings(
        openai_api_key="do-not-print", food_safety_api_key="also-secret", marker="x"
    )
    monkeypatch.setattr(quality, "get_settings", lambda: original)

    settings = quality._settings(False)

    assert settings.openai_api_key is None
    assert settings.food_safety_api_key is None
    assert original.openai_api_key == "do-not-print"


@pytest.mark.asyncio
async def test_sample_runs_live_collection_pipeline_and_reports_no_external_calls(monkeypatch):
    seen = []
    monkeypatch.setattr(
        quality,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=None,
            food_safety_api_key=None,
            openai_model="gpt-5.6-luna",
            model_copy=lambda update: SimpleNamespace(**update, openai_model="gpt-5.6-luna"),
        ),
    )

    async def collect(url):
        seen.append(url)
        return SimpleNamespace(title="Actual product", text="Vitamin C", url=url)

    async def graph(page, product_name, settings):
        assert product_name == "Sample"
        report = valid_report()
        report["ingredients"] = []
        return report

    monkeypatch.setattr(quality, "collect_page", collect)
    monkeypatch.setattr(quality, "run_collection_graph", graph)
    result = await quality.sample(
        [("Sample", "https://vendor.example/item")], use_configured_keys=False
    )

    assert seen == ["https://vendor.example/item"]
    product = result["products"][0]
    assert product["quality_issues"] == []
    assert product["external_calls"] == {
        "openai_configured": False,
        "foodsafety_configured": False,
        "model": None,
    }
    assert result["mode"] == "no_external_calls"
    assert product["quality_assessment"] == "not_assessed_extraction_unavailable_or_empty"


def test_empty_checks_and_required_report_fields_are_reported():
    report = valid_report()
    report.pop("limitations")
    report["checks"] = []
    issues = quality.inspect_report(report)
    assert "checks_missing" in issues
    assert "report_field_missing:limitations" in issues


def test_inspect_report_detects_extracted_values_not_present_in_page():
    report = valid_report()
    report["product"]["name"] = "Invented Name"
    report["claims"] = ["Cures disease"]
    assert quality.inspect_report(report, "Only the real label") == [
        "extracted_value_not_in_page:0",
        "extracted_value_not_in_page:1",
        "extracted_value_not_in_page:2",
    ]


def test_safe_url_drops_query_and_fragment():
    assert quality._safe_url("https://vendor.example/item?token=secret#details") == (
        "https://vendor.example/item"
    )
    assert quality._safe_url("https://user:secret@vendor.example:8443/item?key=secret") == (
        "https://vendor.example:8443/item"
    )
    assert quality._safe_url("https://vendor.example:bad/item") == "<invalid-url>"


def test_parse_args_requires_explicit_opt_in_for_external_calls():
    args = quality.parse_args([])
    assert args.use_configured_keys is False


def test_cli_custom_urls_do_not_become_submitted_names():
    args = quality.parse_args(["--url", "https://vendor.example/product?token=secret"])
    products = [(None, url) for url in args.url]
    assert products == [(None, "https://vendor.example/product?token=secret")]
    assert quality._safe_url(products[0][1]) == "https://vendor.example/product"
