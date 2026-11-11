"""Independent, offline checks for the M1 identity-grounding guards."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from supplement_advisor.agents import collection_graph as runtime
from supplement_advisor.agents import run_collection_graph
from supplement_advisor.agents.structured_extraction import extract_product_table
from supplement_advisor.collection import CollectedPage

ROOT = Path(__file__).parents[1]
REPLAY = ROOT / "work/verification/2026-11-11-identity-guard-replay.json"
STAGE1 = ROOT / "work/verification/2026-11-11-m1-evaluation-stage1.json"
DAYPACK_CACHE = ROOT / "work/verification/m1-evaluation-cache/gs-daypack-af372ebf2cf00cb8.json"


def _extraction(*, product_name=None, manufacturer=None):
    return runtime.Extraction.model_validate(
        {
            "product_name": (
                {"value": product_name, "excerpt": product_name} if product_name else None
            ),
            "manufacturer": (
                {"value": manufacturer, "excerpt": manufacturer} if manufacturer else None
            ),
            "report_number": None,
            "claims": [],
            "ingredients": [],
        }
    )


def test_model_placeholder_product_name_is_withheld():
    placeholder = "상세페이지 참조"
    value = _extraction(product_name=placeholder)
    grounded = runtime._ground_extraction(
        value,
        f"제품명 {placeholder}",
        model_identity=True,
        source_html=f"<tr><th>제품명</th><td>{placeholder}</td></tr>",
    )
    assert grounded["product_name"] is None


@pytest.mark.parametrize(
    ("html", "text", "manufacturer"),
    [
        (
            "<footer>법인명(상호): 주식회사 시나몬랩</footer>",
            "법인명(상호): 주식회사 시나몬랩",
            "주식회사 시나몬랩",
        ),
        (
            "<p>판매원: (주)플레이디</p>",
            "판매원: (주)플레이디",
            "(주)플레이디",
        ),
    ],
)
def test_footer_or_seller_only_company_is_not_manufacturer(html, text, manufacturer):
    grounded = runtime._ground_extraction(
        _extraction(manufacturer=manufacturer),
        text,
        model_identity=True,
        source_html=html,
    )
    assert grounded["manufacturer"] is None


def test_same_row_manufacturer_role_accepts_manufacturer_not_seller():
    html = "<tr><td>제조원: 회사A / 판매원: 회사B</td></tr>"
    text = "제조원: 회사A / 판매원: 회사B"
    assert runtime._ground_extraction(
        _extraction(manufacturer="회사A"), text, model_identity=True, source_html=html
    )["manufacturer"] == "회사A"
    assert runtime._ground_extraction(
        _extraction(manufacturer="회사B"), text, model_identity=True, source_html=html
    )["manufacturer"] is None


def test_explicit_joint_manufacturer_and_seller_role_accepts_shared_company():
    html = "<p>제조원 및 판매원: 회사B</p>"
    text = "제조원 및 판매원: 회사B"
    assert runtime._ground_extraction(
        _extraction(manufacturer="회사B"), text, model_identity=True, source_html=html
    )["manufacturer"] == "회사B"


def test_factory_name_prefix_does_not_match_full_factory_value():
    html = "<tr><td>제조원: 콜마비앤에이치(주)음성공장 / 충청북도</td></tr>"
    text = "제조원: 콜마비앤에이치(주)음성공장 / 충청북도"
    assert runtime._ground_extraction(
        _extraction(manufacturer="콜마비앤에이치(주)"),
        text,
        model_identity=True,
        source_html=html,
    )["manufacturer"] is None


def test_gs_daypack_real_full_factory_value_is_retained():
    cache = json.loads(DAYPACK_CACHE.read_text(encoding="utf-8"))
    source_html = cache["html"]
    manufacturer = "콜마비앤에이치(주)음성공장"
    text = f"제조원: {manufacturer} / 충청북도 음성군"
    grounded = runtime._ground_extraction(
        _extraction(manufacturer=manufacturer),
        text,
        model_identity=True,
        source_html=source_html,
    )
    assert grounded["manufacturer"] == manufacturer


def test_er_hana_direct_table_path_still_extracts_without_model(monkeypatch):
    html = """<table>
      <tr><td colspan="2">이알하나(ER Hana®) 제조 및 표시 사항</td></tr>
      <tr><td>제품명</td><td>이알하나 (ER Hana®)</td></tr>
      <tr><td>제조업소의 명칭과 소재지</td><td>(주)서흥 / 충청북도 청주시</td></tr>
      <tr><td>품목제조신고번호</td><td>200400200062002</td></tr>
      <tr><td>기능정보</td><td>[루바브뿌리추출물(ERr731®)] [비타민D] [비타민K]</td></tr>
    </table>"""
    extracted = extract_product_table(html)
    assert extracted is not None
    assert extracted["manufacturer"]["value"] == "(주)서흥"
    assert extracted["report_number"]["value"] == "200400200062002"

    def forbidden_client(**kwargs):
        pytest.fail("strict table identity must not invoke the model")

    monkeypatch.setattr(runtime, "AsyncOpenAI", forbidden_client)
    page = CollectedPage(
        url="https://shop.example/er-hana",
        title="이알하나 (ER Hana®)",
        text="이알하나 (ER Hana®) 제조업소의 명칭과 소재지 (주)서흥 품목제조신고번호 200400200062002 기능정보 루바브뿌리추출물(ERr731®) 비타민D 비타민K",
        html=html,
        image_urls=[],
    )
    settings = SimpleNamespace(
        openai_api_key=None,
        openai_model="gpt-5.6-luna",
        food_safety_api_key=None,
        external_timeout_seconds=15,
        model_timeout_seconds=15,
        analysis_timeout_seconds=180,
        max_tool_calls=20,
    )
    import asyncio

    report = asyncio.run(run_collection_graph(page, None, settings))
    assert report["extraction_status"] == {"code": "structured_page"}
    assert report["product"]["name"] == "이알하나 (ER Hana®)"
    assert report["product"]["manufacturer"] == "(주)서흥"
    assert report["product"]["report_number"] == "200400200062002"
    assert {item["name"] for item in report["ingredients"]} == {
        "루바브뿌리추출물(ERr731®)",
        "비타민D",
        "비타민K",
    }


def test_saved_offline_replay_is_hash_bound_and_makes_no_provider_calls():
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    stage1 = json.loads(STAGE1.read_text(encoding="utf-8"))
    assert replay["stage1_artifact_sha256"] == hashlib.sha256(STAGE1.read_bytes()).hexdigest()
    assert replay["stage1_manifest_sha256"] == stage1["manifest_sha256"]
    assert replay["collection_graph_sha256"] == hashlib.sha256(
        (ROOT / "src/supplement_advisor/agents/collection_graph.py").read_bytes()
    ).hexdigest()
    assert replay["diagnostic_calls"] == {
        "model": 0,
        "official_api": 0,
        "baseline_rerun": 0,
    }
    for sample in replay["samples"]:
        cache_path = ROOT / sample["source_cache_file"]
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        assert hashlib.sha256(cache["html"].encode("utf-8")).hexdigest() == sample["source_html_sha256"]
        assert sample["source_html_sha256"] == sample["manifest_source_sha256"]
    outcomes = {
        (sample["sample_id"], check["field"]): check["outcome"]
        for sample in replay["samples"]
        for check in sample["checks"]
    }
    assert outcomes == {
        ("kgc-387", "manufacturer"): "kept",
        ("er-15", "manufacturer"): "kept",
        ("gs-womanpack", "manufacturer"): "kept",
        ("gs-womanpack", "product_name"): "withheld",
        ("gs-lutein", "manufacturer"): "kept",
        ("gs-daypack", "manufacturer"): "kept",
        ("er-56", "manufacturer"): "withheld",
    }
    assert "does not replay" in replay["purpose"]

