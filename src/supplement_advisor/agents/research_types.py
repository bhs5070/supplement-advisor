"""Validated internal and public DTOs for evidence review."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RoleId = Literal["composition", "claims", "personal_fit", "safety", "official_quality"]
DispatchableRoleId = Literal["composition", "claims", "safety", "official_quality"]
ToolId = Literal["search_official", "search_literature", "fetch_source", "finish"]
SupervisorActionId = Literal["dispatch", "finish"]
RoleStatusId = Literal[
    "completed", "partial", "insufficient_evidence", "not_applicable", "unavailable", "failed"
]
FindingStatusId = Literal["supported", "contradicted", "mixed", "not_assessable"]
ApplicabilityId = Literal["ingredient_only", "product_label", "product_applicable", "unassessed"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _safe_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("public HTTP(S) URL required")
    if parsed.port not in (None, 80 if parsed.scheme == "http" else 443):
        raise ValueError("unsupported URL port")
    return value


class ResearchSource(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    kind: str
    title: str = Field(max_length=1000)
    url: str = Field(max_length=4096)
    retrieved_at: str = Field(max_length=80)
    provider: str = Field(max_length=100)
    document_id: str | None = Field(default=None, max_length=200)
    pmid: str | None = Field(default=None, max_length=30)
    doi: str | None = Field(default=None, max_length=200)
    published_at: str | None = Field(default=None, max_length=80)
    access_scope: str
    excerpt: str = Field(max_length=500)
    text: str = Field(max_length=24000)

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, value):
        if value not in {"official", "research", "discovery"}:
            raise ValueError("unknown source kind")
        return value

    @field_validator("access_scope")
    @classmethod
    def valid_scope(cls, value):
        if value not in {"discovery", "abstract", "document"}:
            raise ValueError("unknown access scope")
        return value

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return _safe_url(value)


class Quote(StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    excerpt: str = Field(min_length=1, max_length=500)


class Finding(StrictModel):
    statement: str = Field(min_length=1, max_length=1000)
    status: FindingStatusId
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    quotes: list[Quote] = Field(default_factory=list, max_length=10)
    applicability: ApplicabilityId = "unassessed"

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value not in {"supported", "contradicted", "mixed", "not_assessable"}:
            raise ValueError("unknown finding status")
        return value

    @field_validator("applicability")
    @classmethod
    def valid_applicability(cls, value):
        if value not in {"ingredient_only", "product_label", "product_applicable", "unassessed"}:
            raise ValueError("unknown applicability")
        return value


class RoleResult(StrictModel):
    role: RoleId
    status: RoleStatusId
    question: str = Field(max_length=1000)
    findings: list[Finding] = Field(default_factory=list, max_length=10)
    missing_information: list[str] = Field(default_factory=list, max_length=20)
    reasons: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("role")
    @classmethod
    def valid_role(cls, value):
        if value not in {"composition", "claims", "personal_fit", "safety", "official_quality"}:
            raise ValueError("unknown role")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value not in {"completed", "partial", "insufficient_evidence", "not_applicable", "unavailable", "failed"}:
            raise ValueError("unknown role status")
        return value


class RoleAction(StrictModel):
    action: ToolId
    query: str | None = Field(default=None, max_length=300)
    source_id: str | None = Field(default=None, max_length=100)
    result: RoleResult | None = None

    @field_validator("action")
    @classmethod
    def valid_action(cls, value):
        if value not in {"search_official", "search_literature", "fetch_source", "finish"}:
            raise ValueError("unknown action")
        return value

    @model_validator(mode="after")
    def valid_payload(self):
        if self.action in {"search_official", "search_literature"} and not self.query:
            raise ValueError("search action requires query")
        if self.action == "fetch_source" and not self.source_id:
            raise ValueError("fetch action requires source id")
        if self.action == "finish" and self.result is None:
            raise ValueError("finish action requires result")
        return self


class Assignment(StrictModel):
    role: DispatchableRoleId
    question: str = Field(max_length=1000)

    @field_validator("role")
    @classmethod
    def valid_role(cls, value):
        if value not in {"composition", "claims", "safety", "official_quality"}:
            raise ValueError("role cannot be dispatched")
        return value


class SupervisorDecision(StrictModel):
    action: SupervisorActionId
    assignments: list[Assignment] = Field(default_factory=list, max_length=3)
    reason: str = Field(max_length=1000)

    @field_validator("action")
    @classmethod
    def valid_action(cls, value):
        if value not in {"dispatch", "finish"}:
            raise ValueError("unknown supervisor action")
        return value

    @model_validator(mode="after")
    def valid_assignments(self):
        roles = [assignment.role for assignment in self.assignments]
        if self.action == "dispatch" and not 1 <= len(roles) <= 3:
            raise ValueError("dispatch requires one to three roles")
        if self.action == "finish" and roles:
            raise ValueError("finish cannot include assignments")
        if len(set(roles)) != len(roles):
            raise ValueError("duplicate assignment")
        return self


class ResearchResult(StrictModel):
    status: str
    roles: list[RoleResult] = Field(max_length=5)
    sources: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    termination_reason: str | None = None
    decisions: list[dict] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_roles(self):
        expected = {"composition", "claims", "personal_fit", "safety", "official_quality"}
        names = [role.role for role in self.roles]
        if set(names) != expected or len(names) != len(expected):
            raise ValueError("research result must contain each role once")
        if self.status not in {"completed", "partial", "unavailable"}:
            raise ValueError("unknown research status")
        return self


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _doi_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized)


def _source_conflicts(left: ResearchSource, right: ResearchSource) -> bool:
    return any(
        first and second and first != second
        for first, second in (
            (left.pmid, right.pmid),
            (_doi_key(left.doi), _doi_key(right.doi)),
            (left.document_id, right.document_id),
        )
    )


def _same_registered_source(left: ResearchSource, right: ResearchSource) -> bool:
    return (
        left.id == right.id
        or bool(left.pmid and right.pmid and left.pmid == right.pmid)
        or bool(left.doi and right.doi and _doi_key(left.doi) == _doi_key(right.doi))
    )


def _source_quality(source: ResearchSource) -> tuple[int, int, int]:
    access_rank = {"discovery": 0, "abstract": 1, "document": 2}[source.access_scope]
    kind_rank = {"discovery": 0, "research": 1, "official": 2}[source.kind]
    return access_rank, len(source.text), kind_rank


def _promote_source(existing: ResearchSource, incoming: ResearchSource) -> ResearchSource:
    incoming_quality, existing_quality = _source_quality(incoming), _source_quality(existing)
    prefer_incoming = incoming_quality > existing_quality or (
        incoming_quality == existing_quality
        and incoming.id == existing.id
        and incoming.retrieved_at > existing.retrieved_at
    )
    richer, older = (incoming, existing) if prefer_incoming else (existing, incoming)
    return richer.model_copy(update={
        "id": existing.id,
        "pmid": richer.pmid or older.pmid,
        "doi": richer.doi or older.doi,
        "document_id": richer.document_id or older.document_id,
        "published_at": richer.published_at or older.published_at,
    })


def normalize_sources(sources: list[ResearchSource]) -> list[ResearchSource]:
    out: list[ResearchSource] = []
    for source in sources:
        duplicate_indices = [
            index for index, existing in enumerate(out)
            if not _source_conflicts(existing, source)
            and _same_registered_source(existing, source)
        ]
        if len(duplicate_indices) != 1:
            out.append(source)
        else:
            duplicate_index = duplicate_indices[0]
            out[duplicate_index] = _promote_source(out[duplicate_index], source)
    return out


def validate_findings(result: RoleResult, sources: list[ResearchSource], collection: dict) -> RoleResult:
    by_id = {item.id: item for item in sources}
    findings = []
    invalid_any = False
    reasons = list(result.reasons)
    applicability_reason = "완제품 적용성은 M2에서 평가하지 않았습니다."
    for finding in result.findings:
        if finding.applicability == "product_applicable":
            findings.append(finding.model_copy(update={
                "status": "not_assessable", "applicability": "unassessed",
            }))
            if applicability_reason not in reasons:
                reasons = [*reasons, applicability_reason][-20:]
            invalid_any = True
            continue
        source_ids = set(finding.source_ids)
        quote_ids = [quote.source_id for quote in finding.quotes]
        quote_map = {quote.source_id: quote.excerpt for quote in finding.quotes}
        valid = (
            bool(source_ids)
            and source_ids <= by_id.keys()
            and source_ids == quote_map.keys()
            and len(source_ids) == len(finding.source_ids)
            and len(quote_ids) == len(quote_map)
        )
        for source_id in source_ids & by_id.keys():
            source = by_id[source_id]
            quote = quote_map.get(source_id, "")
            valid = (
                valid
                and source.kind != "discovery"
                and source.access_scope != "discovery"
                and bool(_norm(quote))
                and _norm(quote) in _norm(source.text)
            )
        if valid:
            findings.append(finding)
        else:
            invalid_any = True
            findings.append(finding.model_copy(update={"status": "not_assessable", "source_ids": [], "quotes": [], "applicability": "unassessed"}))
    return result.model_copy(update={
        "findings": findings,
        "status": "insufficient_evidence" if invalid_any else result.status,
        "reasons": reasons,
    })


def public_source(source: ResearchSource) -> dict:
    data = source.model_dump(exclude={"text"})
    parsed = urlsplit(data["url"])
    data["url"] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return data


def personal_fit_not_applicable(question: str = "회원 개인 적합성") -> RoleResult:
    return RoleResult(role="personal_fit", status="not_applicable", question=question,
                      reasons=["회원 프로필이 없어 개인 적합성을 평가하지 않았습니다."])
