import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from pydantic import ValidationError

from supplement_advisor.agents.evidence_tools import EvidenceTools, ResearchToolError
from supplement_advisor.agents.research_types import (
    Finding,
    ResearchSource,
    RoleAction,
    RoleResult,
    SupervisorDecision,
    normalize_sources,
    personal_fit_not_applicable,
    public_source,
    validate_findings,
)


def source(**overrides):
    values = {
        "id": "s1", "kind": "official", "title": "자료", "url": "https://mfds.go.kr/a?secret=x",
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "provider": "test",
        "access_scope": "document", "excerpt": "비타민 C 표시", "text": "비타민 C 표시 및 함량",
    }
    values.update(overrides)
    return ResearchSource(**values)


def result(finding, role="claims"):
    return RoleResult(role=role, status="completed", question="질문", findings=[finding])


def test_rejects_unknown_roles_and_tools_and_untrusted_urls():
    with pytest.raises(ValidationError):
        RoleResult(role="invented", status="completed", question="q")
    with pytest.raises(ValidationError):
        ResearchSource(**{**source().model_dump(), "url": "https://user:pass@mfds.go.kr/a"})
    with pytest.raises(ValidationError):
        RoleAction(action="unknown")
    with pytest.raises(ValidationError):
        RoleAction(action="finish")
    with pytest.raises(ValidationError):
        SupervisorDecision(action="dispatch", assignments=[{"role": "personal_fit", "question": "q"}], reason="r")
    assert personal_fit_not_applicable().status == "not_applicable"


def test_rejects_oversized_fields_and_unknown_source_or_false_quote():
    with pytest.raises(ValidationError):
        source(text="x" * 24001)
    unknown = result(Finding(statement="x", status="supported", source_ids=["missing"], quotes=[]))
    assert validate_findings(unknown, [source()], {}).findings[0].status == "not_assessable"
    invalid = result(Finding(statement="표시", status="supported", source_ids=["s1"],
                             quotes=[{"source_id": "s1", "excerpt": "원문에 없는 문장"}]))
    checked = validate_findings(invalid, [source()], {})
    assert checked.status == "insufficient_evidence"
    assert checked.findings[0].status == "not_assessable"


def test_duplicate_quote_source_ids_downgrade_the_finding():
    duplicate_quotes = Finding(statement="표시", status="supported", source_ids=["s1"], quotes=[
        {"source_id": "s1", "excerpt": "비타민 C 표시"},
        {"source_id": "s1", "excerpt": "비타민 C 표시"},
    ])
    checked = validate_findings(result(duplicate_quotes), [source()], {})
    assert checked.findings[0].status == "not_assessable"
    assert checked.status == "insufficient_evidence"


def test_official_general_guidance_cannot_become_product_applicable():
    finding = Finding(
        statement="제품 효과", status="supported", source_ids=["ods"],
        quotes=[{"source_id": "ods", "excerpt": "비타민 C 표시 및 함량"}],
        applicability="product_applicable",
    )
    checked = validate_findings(result(finding), [source(id="ods", kind="official")], {})
    assert checked.findings[0].status == "not_assessable"
    assert checked.findings[0].applicability == "unassessed"
    assert checked.findings[0].source_ids == ["ods"]
    assert len(checked.findings[0].quotes) == 1
    assert any("완제품" in reason or "제품" in reason for reason in checked.reasons)


def test_discovery_cannot_ground_factual_findings_and_raw_text_is_private():
    found = Finding(statement="비타민 C 표시", status="supported", source_ids=["d1"],
                    quotes=[{"source_id": "d1", "excerpt": "비타민 C 표시"}])
    checked = validate_findings(result(found), [source(id="d1", kind="discovery", access_scope="discovery")], {})
    assert checked.findings[0].status == "not_assessable"
    assert checked.model_dump(mode="json")["findings"][0]["source_ids"] == []
    assert "text" not in source().model_dump(mode="json", exclude={"text"})
    scoped_discovery = source(id="d2", kind="official", access_scope="discovery")
    finding = Finding(statement="비타민 C 표시", status="supported", source_ids=["d2"],
                      quotes=[{"source_id": "d2", "excerpt": "비타민 C 표시"}])
    assert validate_findings(result(finding), [scoped_discovery], {}).findings[0].status == "not_assessable"


def test_merges_matching_identifiers_but_keeps_conflicting_ids_separate():
    items = [source(id="one", pmid="123", doi="10.1/a"),
             source(id="two", pmid="123", doi="10.1/a", title="다른 사본"),
             source(id="three", pmid="123", doi="10.1/b")]
    merged = normalize_sources(items)
    assert [item.id for item in merged] == ["one", "three"]
    assert merged[0].title == "자료"


def test_deduplicates_canonical_doi_forms_without_merging_conflicting_dois():
    items = [source(id="doi-a", doi="https://doi.org/10.1234/ABC"),
             source(id="doi-b", doi="10.1234/abc", title="복제 기록"),
             source(id="conflict-a", pmid="777", doi="10.1234/left"),
             source(id="conflict-b", pmid="777", doi="10.1234/right")]
    merged = normalize_sources(items)
    assert [item.id for item in merged] == ["doi-a", "conflict-a", "conflict-b"]


def test_source_with_identifiers_matching_two_registry_entries_is_not_guessed_into_either():
    items = [
        source(id="pmid-record", pmid="123"),
        source(id="doi-record", doi="10.1/paper"),
        source(id="ambiguous", pmid="123", doi="10.1/paper"),
    ]
    merged = normalize_sources(items)
    assert [item.id for item in merged] == ["pmid-record", "doi-record", "ambiguous"]


def test_public_source_drops_text_and_url_query_and_fragment():
    public = public_source(source())
    assert "text" not in public
    assert public["url"] == "https://mfds.go.kr/a"


def test_tavily_unconfigured_and_empty_results_are_distinct():
    async def run():
        tool = EvidenceTools(type("Settings", (), {"tavily_api_key": None, "external_timeout_seconds": 15})(), lambda *_: True, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"results": []})))
        with pytest.raises(ResearchToolError) as error:
            await tool.search_official("비타민")
        assert error.value.code == "not_configured"
        tool = EvidenceTools(type("Settings", (), {"tavily_api_key": "test", "external_timeout_seconds": 15})(), lambda *_: True, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"results": []})))
        assert await tool.search_official("비타민") == []
    asyncio.run(run())


@pytest.mark.parametrize("payload", [None, [], {"results": None}])
def test_tavily_malformed_top_level_or_results_returns_safe_error(payload):
    async def run():
        settings = type("Settings", (), {"tavily_api_key": "test", "external_timeout_seconds": 5})()
        tool = EvidenceTools(settings, lambda *_: True,
                             transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
        with pytest.raises(ResearchToolError) as error:
            await tool.search_official("query")
        assert error.value.code == "invalid_response"
    asyncio.run(run())


@pytest.mark.parametrize("payload", [None, [], {"resultList": None}, {"resultList": {"result": None}}])
def test_europe_pmc_malformed_top_level_or_nested_results_returns_safe_error(payload):
    async def run():
        settings = type("Settings", (), {"external_timeout_seconds": 5})()
        tool = EvidenceTools(settings, lambda *_: True,
                             transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
        with pytest.raises(ResearchToolError) as error:
            await tool.search_literature("query")
        assert error.value.code == "invalid_response"
    asyncio.run(run())


def test_budget_denial_prevents_network_request_and_each_http_request_is_reserved():
    import asyncio

    async def run():
        requests = []
        calls = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"results": [{"title": "정보", "url": "https://mfds.go.kr/a", "content": "표시"}]})
        settings = type("Settings", (), {"tavily_api_key": "test", "external_timeout_seconds": 15})()
        denied = EvidenceTools(settings, lambda *_: False, transport=httpx.MockTransport(handler))
        with pytest.raises(ResearchToolError):
            await denied.search_official("비타민")
        assert requests == []
        allowed = EvidenceTools(settings, lambda owner, timeout: calls.append((owner, timeout)) or True, owner="claims", transport=httpx.MockTransport(handler))
        found = await allowed.search_official("비타민")
        assert len(found) == 1
        assert len(requests) == 1
        assert calls == [("claims", 15)]
    asyncio.run(run())


def test_rejects_ssrf_and_ad_domains_from_official_search():
    import asyncio

    async def run():
        settings = type("Settings", (), {"tavily_api_key": "test", "external_timeout_seconds": 15})()
        tool = EvidenceTools(settings, lambda *_: True, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"results": [
            {"title": "내부", "url": "http://127.0.0.1/admin", "content": "x"},
            {"title": "광고", "url": "https://shop.example/item", "content": "광고"},
            {"title": "공식", "url": "https://mfds.go.kr/a", "content": "원문"},
        ]})))
        found = await tool.search_official("질문")
        assert [item.url for item in found] == ["https://mfds.go.kr/a"]
    asyncio.run(run())


def test_literature_partial_fields_and_provider_failure_are_safe():
    async def run():
        settings = type("Settings", (), {"external_timeout_seconds": 5})()
        tool = EvidenceTools(settings, lambda *_: True, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"resultList": {"result": [
            {"id": "abc", "title": "단편 자료"},
            {"pmid": "321", "title": "초록", "abstractText": "텍스트 <i>정리</i>"},
        ]}})))
        found = await tool.search_literature("vitamin")
        assert len(found) == 2
        assert found[0].title == "단편 자료"
        assert found[0].access_scope == "discovery"
        assert found[1].text == "텍스트 정리"
        broken = EvidenceTools(settings, lambda *_: True, transport=httpx.MockTransport(lambda _: httpx.Response(503, text="private body")))
        with pytest.raises(ResearchToolError) as error:
            await broken.search_literature("vitamin")
        assert error.value.code == "provider_error"
        assert "private body" not in str(error.value)
    asyncio.run(run())


def test_fetch_source_only_accepts_public_registered_sources_and_reserves(monkeypatch):
    async def run():
        settings = type("Settings", (), {"external_timeout_seconds": 15})()
        calls = []
        import supplement_advisor.agents.evidence_tools as module
        from supplement_advisor.collection import CollectedPage, CollectionError

        async def denied_collection(url, *, timeout, max_bytes, reserve_request):
            if not reserve_request():
                raise CollectionError("budget_exhausted", "budget")
            raise AssertionError("denied request must stop before HTTP")

        monkeypatch.setattr(module, "collect_page", denied_collection)
        tool = EvidenceTools(settings, lambda owner, timeout: calls.append((owner, timeout)) or False, owner="safety")
        with pytest.raises(ResearchToolError) as error:
            await tool.fetch_source(source(url="http://127.0.0.1/a"))
        assert error.value.code == "unsafe_source"
        safe_tool = EvidenceTools(settings, lambda owner, timeout: calls.append((owner, timeout)) or False, owner="safety")
        with pytest.raises(ResearchToolError) as error:
            await safe_tool.fetch_source(source())
        assert error.value.code == "budget_exhausted"
        assert calls == [("safety", 15)]
        async def collected(url, *, timeout, max_bytes, reserve_request):
            assert reserve_request()
            return CollectedPage(url, "공식 자료", "공식 본문", "<p>공식 본문</p>", [])

        monkeypatch.setattr(module, "collect_page", collected)
        allowed = EvidenceTools(settings, lambda *_: True, owner="official_quality")
        discovered = source(id="tavily1", kind="discovery", access_scope="discovery", text="검색 미리보기")
        fetched = await allowed.fetch_source(discovered)
        assert fetched.kind == "official"
        assert fetched.access_scope == "document"
        assert fetched.text == "공식 본문"

        async def redirected_collection(url, *, timeout, max_bytes, reserve_request):
            assert reserve_request()
            return CollectedPage("https://shop.example/redirected", "광고", "광고 본문", "<p>광고</p>", [])

        monkeypatch.setattr(module, "collect_page", redirected_collection)
        with pytest.raises(ResearchToolError) as error:
            await allowed.fetch_source(discovered)
        assert error.value.code == "unsafe_source"
    asyncio.run(run())


def test_pubmed_fallback_reserves_each_http_exchange_and_parses_partial_xml():
    async def run():
        requests = []
        reservations = []
        def handler(request):
            requests.append(request.url.path)
            if request.url.host == "www.ebi.ac.uk":
                return httpx.Response(503)
            if request.url.path.endswith("esearch.fcgi"):
                return httpx.Response(200, text="<eSearchResult><IdList><Id>555</Id></IdList></eSearchResult>")
            if request.url.path.endswith("esummary.fcgi"):
                return httpx.Response(200, text="<eSummaryResult><DocSum uid='555'><Item Name='Title'>요약 제목</Item></DocSum></eSummaryResult>")
            return httpx.Response(200, text="<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>555</PMID><Article><ArticleTitle>논문 제목</ArticleTitle><Abstract><AbstractText>초록 내용</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>")
        settings = type("Settings", (), {"external_timeout_seconds": 5})()
        tool = EvidenceTools(settings, lambda owner, timeout: reservations.append((owner, timeout)) or True,
                             owner="composition", transport=httpx.MockTransport(handler))
        found = await tool.search_literature("ingredient")
        assert len(found) == 1
        assert found[0].pmid == "555"
        assert found[0].text == "초록 내용"
        assert len(requests) == 4
        assert reservations == [("composition", 5)] * 4
    asyncio.run(run())


def test_full_text_requires_pmcid_and_does_not_use_pmid_as_europepmc_id():
    async def run():
        requests = []
        reservations = []
        def handler(request):
            requests.append(request.url.path)
            return httpx.Response(200, text="<article><body><p>Full text</p></body></article>")
        settings = type("Settings", (), {"external_timeout_seconds": 4})()
        tool = EvidenceTools(settings, lambda owner, timeout: reservations.append(owner) or True,
                             transport=httpx.MockTransport(handler))
        with pytest.raises(ResearchToolError) as error:
            await tool.fetch_source(source(kind="research", provider="pubmed", pmid="555", access_scope="abstract"))
        assert error.value.code == "document_unavailable"
        assert requests == []
        fulltext = await tool.fetch_source(source(kind="research", provider="europepmc", pmid="555",
                                                  document_id="PMC123", access_scope="abstract"))
        assert requests == ["/europepmc/webservices/rest/PMC123/fullTextXML"]
        assert fulltext.text == "Full text"
        assert fulltext.access_scope == "document"
        assert reservations == ["evidence"]
    asyncio.run(run())
