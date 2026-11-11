"""Bounded, budget-reserved public evidence providers."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import httpx

from ..collection import CollectionError, collect_page
from .research_types import ResearchSource, normalize_sources

MAX_BODY = 1_000_000
OFFICIAL_HOSTS = {"foodsafetykorea.go.kr", "mfds.go.kr", "ods.od.nih.gov"}
AD_HOST_PARTS = {"shop", "shopping", "store", "mall", "smartstore", "coupang", "amazon", "iherb"}
_pubmed_next = 0.0
_pubmed_lock = threading.Lock()


class ResearchToolError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _valid_public_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        if parsed.port not in (None, 80 if parsed.scheme == "http" else 443):
            return False
        host = parsed.hostname.lower().rstrip(".")
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                return False
        except ValueError:
            if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal", ".localhost")):
                return False
        return True
    except ValueError:
        return False


def _ad_domain(host: str) -> bool:
    parts = set(host.lower().split("."))
    return bool(parts & AD_HOST_PARTS)


def _source_id(provider: str, identity: str, url: str) -> str:
    return hashlib.sha256(f"{provider}:{identity}:{url}".encode()).hexdigest()[:24]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceTools:
    def __init__(self, settings, reserve, *, owner="evidence", transport=None):
        self.settings = settings
        self.reserve = reserve
        self.owner = owner
        self.transport = transport
        raw_timeout = float(getattr(settings, "external_timeout_seconds", 15))
        if not math.isfinite(raw_timeout) or raw_timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self.timeout = min(raw_timeout, 15)

    async def _request(self, method: str, url: str, *, params=None, headers=None, json_body=None):
        if not self.reserve(self.owner, self.timeout):
            raise ResearchToolError("budget_exhausted")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout), follow_redirects=False,
                                         trust_env=False, transport=self.transport) as client:
                async with client.stream(method, url, params=params, headers=headers, json=json_body) as response:
                    if response.is_redirect:
                        raise ResearchToolError("provider_error")
                    if response.status_code == 429:
                        raise ResearchToolError("rate_limited")
                    if not 200 <= response.status_code < 300:
                        raise ResearchToolError("provider_error")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > MAX_BODY:
                            raise ResearchToolError("response_too_large")
                        data.extend(chunk)
                    return bytes(data)
        except ResearchToolError:
            raise
        except httpx.TimeoutException:
            raise ResearchToolError("timeout") from None
        except httpx.HTTPError:
            raise ResearchToolError("connection_failed") from None

    async def search_official(self, query: str) -> list[ResearchSource]:
        key = getattr(self.settings, "tavily_api_key", None)
        if not key:
            raise ResearchToolError("not_configured")
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise ResearchToolError("invalid_query")
        payload = {"api_key": key, "query": query, "search_depth": "basic", "max_results": 5,
                   "include_answer": False, "include_raw_content": False, "auto_parameters": False,
                   "include_domains": sorted(OFFICIAL_HOSTS)}
        raw = await self._request("POST", "https://api.tavily.com/search", json_body=payload,
                                  headers={"Accept": "application/json"})
        try:
            body = json.loads(raw)
            if not isinstance(body, dict) or not isinstance(body.get("results"), list):
                raise ValueError
            results = body["results"]
        except (ValueError, TypeError):
            raise ResearchToolError("invalid_response") from None
        output = []
        for item in results[:5]:
            if not isinstance(item, dict):
                continue
            url = item.get("url", "")
            if not isinstance(url, str) or not _valid_public_url(url):
                continue
            host = (urlsplit(url).hostname or "").lower()
            if not any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_HOSTS):
                continue
            if _ad_domain(host):
                continue
            title, excerpt = str(item.get("title") or "")[:1000], str(item.get("content") or "")[:500]
            output.append(ResearchSource(id=_source_id("tavily", url, url), kind="discovery", title=title,
                url=url, retrieved_at=_now(), provider="tavily", access_scope="discovery", excerpt=excerpt, text=excerpt))
        return normalize_sources(output)

    async def search_literature(self, query: str) -> list[ResearchSource]:
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise ResearchToolError("invalid_query")
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        try:
            raw = await self._request("GET", url, params={"query": query, "format": "json", "pageSize": 5,
                                                           "resultType": "core"}, headers={"Accept": "application/json"})
        except ResearchToolError:
            return await self._search_pubmed(query)
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError
            result_list = body.get("resultList")
            if not isinstance(result_list, dict) or not isinstance(result_list.get("result"), list):
                raise ValueError
            entries = result_list["result"]
        except (ValueError, TypeError):
            raise ResearchToolError("invalid_response") from None
        output = []
        for item in entries[:5]:
            if not isinstance(item, dict):
                continue
            pmid, doi = item.get("pmid"), item.get("doi")
            identity = str(pmid or doi or item.get("id") or "")
            if not identity:
                continue
            title = str(item.get("title") or "제목 없음")[:1000]
            abstract = item.get("abstractText") or ""
            if isinstance(abstract, list):
                abstract = " ".join(map(str, abstract))
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(abstract))).strip()[:24000]
            url_value = f"https://europepmc.org/article/MED/{pmid}" if pmid else f"https://doi.org/{quote(str(doi), safe='/') }"
            pmcid = item.get("pmcid")
            output.append(ResearchSource(id=_source_id("europepmc", identity, url_value), kind="research", title=title,
                url=url_value, retrieved_at=_now(), provider="europepmc", pmid=str(pmid) if pmid else None,
                document_id=str(pmcid) if pmcid else None, doi=str(doi) if doi else None,
                published_at=str(item.get("firstPublicationDate") or "") or None,
                access_scope="abstract" if text else "discovery", excerpt=text[:500] or title, text=text or title))
        return normalize_sources(output)

    async def _pubmed_request(self, endpoint: str, params: dict[str, str]) -> bytes:
        global _pubmed_next
        with _pubmed_lock:
            delay = max(0.0, _pubmed_next - time.monotonic())
            _pubmed_next = time.monotonic() + max(delay, 0.5)
        if delay:
            import asyncio
            await asyncio.sleep(delay)
        return await self._request("GET", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/" + endpoint,
                                   params=params, headers={"Accept": "application/xml"})

    async def _search_pubmed(self, query: str) -> list[ResearchSource]:
        try:
            raw = await self._pubmed_request("esearch.fcgi", {"db": "pubmed", "term": query, "retmax": "5", "retmode": "xml"})
            root = ET.fromstring(raw)
            pmids = [node.text for node in root.findall(".//Id") if node.text]
            if not pmids:
                return []
            summary = await self._pubmed_request("esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
            summary_root = ET.fromstring(summary)
            titles = {doc.get("uid"): "".join(doc.findtext("Item[@Name='Title']") or "" for _ in [0]) for doc in summary_root.findall(".//DocSum")}
            abstracts = await self._pubmed_request("efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"})
            abstract_root = ET.fromstring(abstracts)
            output = []
            for article in abstract_root.findall(".//PubmedArticle")[:5]:
                pmid = article.findtext(".//PMID")
                if not pmid:
                    continue
                title = " ".join("".join(node.itertext()) for node in article.findall(".//ArticleTitle")).strip() or titles.get(pmid) or "제목 없음"
                abstract = " ".join("".join(node.itertext()) for node in article.findall(".//AbstractText")).strip()
                url_value = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                pmcid = article.findtext(".//ArticleId[@IdType='pmc']")
                output.append(ResearchSource(id=_source_id("pubmed", pmid, url_value), kind="research", title=title[:1000],
                    url=url_value, retrieved_at=_now(), provider="pubmed", pmid=pmid,
                    document_id=pmcid,
                    published_at=article.findtext(".//PubDate/Year"), access_scope="abstract" if abstract else "discovery",
                    excerpt=abstract[:500] or title, text=abstract[:24000] or title))
            return normalize_sources(output)
        except ResearchToolError:
            raise
        except (ET.ParseError, TypeError, ValueError):
            raise ResearchToolError("invalid_response") from None

    async def fetch_source(self, source: ResearchSource) -> ResearchSource:
        if not isinstance(source, ResearchSource):
            raise ResearchToolError("unknown_source")
        if source.kind == "research":
            if source.document_id and re.fullmatch(r"PMC\d+", source.document_id, flags=re.I):
                raw = await self._request("GET", "https://www.ebi.ac.uk/europepmc/webservices/rest/" + quote(source.document_id, safe="") + "/fullTextXML")
                try:
                    root = ET.fromstring(raw)
                    text = " ".join(" ".join(node.itertext()).strip() for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"p", "abstract"})
                except ET.ParseError:
                    raise ResearchToolError("invalid_response") from None
                if not text.strip():
                    raise ResearchToolError("document_unavailable")
                return source.model_copy(update={"access_scope": "document", "text": text[:24000], "excerpt": text[:500]})
            raise ResearchToolError("document_unavailable")
        host = (urlsplit(source.url).hostname or "").lower()
        if source.kind not in {"official", "discovery"} or not _valid_public_url(source.url) or not any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_HOSTS):
            raise ResearchToolError("unsafe_source")
        try:
            page = await collect_page(
                source.url,
                timeout=self.timeout,
                max_bytes=MAX_BODY,
                reserve_request=lambda: self.reserve(self.owner, self.timeout),
            )
        except CollectionError as error:
            raise ResearchToolError(error.code) from None
        final_host = (urlsplit(page.url).hostname or "").lower()
        if not any(final_host == domain or final_host.endswith("." + domain) for domain in OFFICIAL_HOSTS):
            raise ResearchToolError("unsafe_source")
        return source.model_copy(update={"kind": "official", "url": page.url, "access_scope": "document", "text": page.text[:24000], "excerpt": page.text[:500], "title": page.title[:1000] or source.title})
