import json
from pathlib import Path
from types import SimpleNamespace

from supplement_advisor.agents import collection_graph as runtime
from supplement_advisor.agents import run_collection_graph
from supplement_advisor.agents.structured_extraction import extract_product_table
from supplement_advisor.collection import CollectedPage

TABLE = Path("work/verification/2026-11-10-real-product-table.html").read_text() + (
    '<table><tr><td colspan="2">이알하나(ER Hana®) 제조 및 표시 사항</td></tr>'
    '<tr><td><strong>③ 제조업소의 명칭과 소재지</strong></td>'
    '<td>(주)서흥 / 충청북도 청주시</td></tr></table>'
)
VISIBLE = "이알하나(ER Hana®) 제품 정보 제품명 이알하나 (ER Hana®) 건강기능식품 루바브뿌리추출물(ERr731®)(제2024-17호), 비타민D, 비타민K 품목제조신고번호 200400200062002 [루바브뿌리추출물(ERr731®)(제2024-17호)] [비타민D] [비타민K] 제조업소의 명칭과 소재지 (주)서흥 / 충청북도 청주시"


def _page(html=TABLE, text=VISIBLE):
    return CollectedPage("https://shop.example/p", "이알하나", text, html, [])


def _settings(**values):
    defaults = dict(
        openai_api_key=None, openai_model="gpt-5.6-luna", food_safety_api_key=None,
        external_timeout_seconds=15, analysis_timeout_seconds=180, max_tool_calls=20,
    )
    return SimpleNamespace(**(defaults | values))


def test_real_product_table_extracts_explicit_functional_ingredients():
    value = extract_product_table(TABLE)
    assert value["product_name"]["value"] == "이알하나 (ER Hana®)"
    assert value["report_number"]["value"] == "200400200062002"
    assert set(item["name"] for item in value["ingredients"]) == {
        "루바브뿌리추출물(ERr731®)(제2024-17호)", "비타민D", "비타민K"
    }
    assert all(item["amount"] is None and item["basis"] is None for item in value["ingredients"])


async def test_direct_table_data_skips_model_and_keeps_official_positive(monkeypatch):
    settings = _settings(food_safety_api_key="official-secret")
    model_calls = []
    class NoModel:
        def __init__(self, **kwargs):
            model_calls.append(kwargs)
            raise AssertionError("strict table extraction should not call the model")
    monkeypatch.setattr(runtime, "AsyncOpenAI", NoModel)
    record = {
        "PRDLST_NM": "공식 루바브 밸런스", "BSSH_NM": "(주)서흥",
        "PRDLST_REPORT_NO": "200400200062002",
        "RAWMTRL_NM": "비타민D, 루바브뿌리추출물(ERr731Ⓡ)(제2024-17호), 비타민K",
        "LAST_UPDT_DTM": "20261101",
    }
    def handler(request):
        import httpx
        payload = json.dumps({"I0030": {"RESULT": {"CODE": "INFO-000"}, "total_count": 1, "row": [record]}}).encode()
        return httpx.Response(200, stream=httpx.ByteStream(payload))
    import httpx
    monkeypatch.setattr(runtime.httpx, "AsyncHTTPTransport", lambda **kw: httpx.MockTransport(handler))
    page = _page()
    report = await run_collection_graph(page, None, settings)
    assert not model_calls
    assert report["extraction_status"] == {"code": "structured_page"}
    assert report["official_match"]["state"] == "matched", report["official_match"]
    assert report["official_match"]["name_difference"] == {
        "page_name": "이알하나 (ER Hana®)", "official_name": "공식 루바브 밸런스"
    }
    assert report["score"] is None and report["verdict"] == "hold"


async def test_table_parser_rejects_wrong_manufacturer_or_unlabeled_number():
    wrong_manufacturer = TABLE.replace("③ 제조업소의 명칭과 소재지", "③ 판매업소의 명칭과 소재지")
    no_number_label = TABLE.replace("품목제조신고번호 200400200062002", "사업자등록번호 200400200062002")
    assert extract_product_table(wrong_manufacturer) is None
    assert extract_product_table(no_number_label) is None


async def test_direct_table_parse_needs_no_model_key_and_unlabeled_page_stays_unavailable(monkeypatch):
    class ForbiddenModel:
        def __init__(self, **kwargs):
            raise AssertionError("model must not be called for strict table facts")
    monkeypatch.setattr(runtime, "AsyncOpenAI", ForbiddenModel)
    report = await run_collection_graph(_page(), None, _settings())
    assert report["extraction_status"] == {"code": "structured_page"}
    assert report["product"]["report_number"] == "200400200062002"
    no_table = CollectedPage("https://shop.example/plain", "plain", "제품 설명만 있음", "<p>제품 설명만 있음</p>", [])
    fallback = await run_collection_graph(no_table, None, _settings())
    assert fallback["extraction_status"] == {"code": "not_configured"}


async def test_ambiguous_tables_and_script_instructions_are_not_extracted():
    duplicated = TABLE + TABLE
    malicious = TABLE.replace("</table>", "</table><script><table><tr><td>제품명</td><td>evil</td></tr></table></script>", 1)
    assert extract_product_table(duplicated) is None
    parsed = extract_product_table(malicious)
    assert parsed and parsed["product_name"]["value"] == "이알하나 (ER Hana®)"
