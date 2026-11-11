"""Independent contract regressions for automatic official matching."""

from supplement_advisor.agents import collection_graph as runtime


def test_product_identity_normalization_preserves_meaningful_punctuation():
    """Only spacing and corporate markers are equivalent in product identities."""
    assert runtime._identity_normalized("에브리타임 샷") == runtime._identity_normalized("에브리타임샷")
    assert runtime._identity_normalized("㈜한국인삼공사") == runtime._identity_normalized("한국인삼공사")
    assert runtime._identity_normalized("홍삼(농축)") != runtime._identity_normalized("홍삼농축")
    assert runtime._identity_normalized("A-B") != runtime._identity_normalized("AB")


def test_ingredient_comparison_preserves_parenthetical_identity_qualifiers():
    """Parentheses can distinguish an ingredient form and cannot be dropped wholesale."""
    assert runtime._ingredient_name_key("발효홍삼") != runtime._ingredient_name_key("홍삼")
    assert runtime._ingredient_name_key("홍삼(농축)") != runtime._ingredient_name_key("홍삼")


def test_common_base_ingredients_do_not_supply_two_distinctive_matches():
    extracted = {
        "ingredients": [
            {"name": "정제수", "amount": None, "unit": None, "basis": None},
            {"name": "홍삼", "amount": None, "unit": None, "basis": None},
        ]
    }
    record = {"ETC_RAWMTRL_NM": "정제수, 홍삼"}
    assert runtime._additional_evidence(extracted, record) is False


def test_numberless_match_does_not_claim_the_page_report_number_matched():
    state = {
        "extraction": {"product_name": "표시 제품", "manufacturer": "표시 제조사", "report_number": None,
                       "claims": [], "ingredients": []},
        "extraction_code": "extracted",
        "source": {"id": "product-page", "url": "https://example.org/p", "title": "제품 페이지",
                   "kind": "advertising", "retrieved_at": "2026-11-09T00:00:00Z", "excerpt": "제품 정보"},
        "official": {
            "status": "verified", "code": "registration_matched", "matched": None,
            "retrieved_at": "2026-11-09T00:00:00Z",
            "official_match": runtime._match("matched", "unique_complete_corroborated_candidate"),
        },
    }
    report = runtime._report(state, None)
    detail = next(c["detail"] for c in report["checks"] if c["name"] == "공식 등록 대조")
    assert "원문 제품명·제조사" in detail
    assert "원문 제품 정보에 덮어쓰지 않았습니다" in detail
    assert "신고번호가 공식 자료와 일치합니다" not in detail


def test_amount_evidence_does_not_borrow_another_ingredient_value():
    extracted = {
        "ingredients": [
            {"name": "아연", "amount": "100", "unit": "mg", "basis": None},
        ]
    }
    record = {
        # Zinc is 10 mg; the 100 mg belongs to the next ingredient.
        "RAWMTRL_NM": "아연 10 mg, 비타민C 100 mg",
    }
    evidence = runtime._additional_evidence_rows(extracted, record, ["product-page"])
    amount_rows = [item for item in evidence if item["field"] == "ingredient_amount"]
    assert not amount_rows or all(item["outcome"] != "match" for item in amount_rows)


def test_amount_evidence_requires_exact_unit_token():
    extracted = {
        "ingredients": [
            {"name": "아연", "amount": "10", "unit": "g", "basis": None},
        ]
    }
    record = {"RAWMTRL_NM": "아연 10 mg"}
    evidence = runtime._additional_evidence_rows(extracted, record, ["product-page"])
    amount_rows = [item for item in evidence if item["field"] == "ingredient_amount"]
    assert amount_rows and all(item["outcome"] != "match" for item in amount_rows)


def test_amount_without_unit_cannot_corroborate_a_measured_quantity():
    extracted = {
        "ingredients": [
            {"name": "아연", "amount": "10", "unit": None, "basis": None},
        ]
    }
    record = {"RAWMTRL_NM": "아연 10 mg"}
    assert runtime._additional_evidence(extracted, record) is False


def test_only_exact_ingredient_names_match_not_substrings():
    extracted = {"ingredients": [{"name": "아연", "amount": None, "unit": None, "basis": None}]}
    record = {"ETC_RAWMTRL_NM": "글루콘산아연", "RAWMTRL_NM": "홍삼"}
    assert runtime._additional_evidence(extracted, record) is False
