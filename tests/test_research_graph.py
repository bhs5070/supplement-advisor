import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import RateLimitError

from supplement_advisor.agents import run_research_graph
from supplement_advisor.agents.research_types import RoleAction, RoleResult, SupervisorDecision


class ParsedResponses:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=next(self.values), status="completed")


class Client:
    def __init__(self, api_key, timeout, max_retries):
        assert max_retries == 0
        self.responses = parsed

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def config(**kwargs):
    values = dict(
        openai_api_key="test-key", openai_model="test-model", model_timeout_seconds=30,
        external_timeout_seconds=15, analysis_timeout_seconds=180, max_tool_calls=20,
        reserve_budget=lambda **kw: True, save_snapshot=lambda snapshot: True,
    )
    values.update(kwargs)
    return SimpleNamespace(**values)


def finding_result(role="claims"):
    return RoleResult(role=role, status="insufficient_evidence", question="claim check",
                      reasons=["no sources available"])


@pytest.mark.asyncio
async def test_supervisor_dispatches_only_selected_roles_and_never_models_personal_fit(monkeypatch):
    global parsed
    parsed = ParsedResponses([
        SupervisorDecision(action="dispatch", reason="check claim and safety", assignments=[
            {"role": "claims", "question": "claim support"},
            {"role": "safety", "question": "safety signals"},
        ]),
        RoleAction(action="finish", result=finding_result("claims")),
        RoleAction(action="finish", result=finding_result("safety")),
        SupervisorDecision(action="finish", reason="remaining roles lack input"),
    ])
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}, "claims": ["claim"]}, config())
    assert len(parsed.calls) == 4
    assert {row["role"] for row in result["report"]["research"]["roles"]} == {
        "composition", "claims", "personal_fit", "safety", "official_quality"
    }
    roles = {row["role"]: row for row in result["report"]["research"]["roles"]}
    assert roles["personal_fit"]["status"] == "not_applicable"
    assert roles["composition"]["status"] == "insufficient_evidence"


@pytest.mark.asyncio
async def test_missing_model_key_does_not_report_fake_success():
    result = await run_research_graph({"product": {}}, config(openai_api_key=None))
    assert result["report"]["research"]["status"] == "unavailable"
    assert result["report"]["research"]["termination_reason"] == "not_configured"


def test_duplicate_or_unsupported_assignment_is_rejected():
    with pytest.raises(ValueError):
        SupervisorDecision(action="dispatch", reason="bad", assignments=[
            {"role": "claims", "question": "a"}, {"role": "claims", "question": "b"}
        ])
    with pytest.raises(ValueError):
        SupervisorDecision(action="dispatch", reason="bad", assignments=[
            {"role": "personal_fit", "question": "member"}
        ])


@pytest.mark.asyncio
async def test_completed_snapshot_is_returned_without_model_calls(monkeypatch):
    global parsed
    parsed = ParsedResponses([])
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    first = await run_research_graph({"product": {}}, config(openai_api_key=None))
    snapshot = first["snapshot"]
    snapshot["phase"] = "report"
    snapshot["report"] = first["report"]
    resumed = await run_research_graph({"product": {}}, config(), snapshot=snapshot)
    assert not parsed.calls
    assert resumed["report"] == first["report"]


@pytest.mark.asyncio
async def test_invalid_or_incompatible_snapshot_fails_closed_without_calls(monkeypatch):
    global parsed
    parsed = ParsedResponses([])
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}}, config(), snapshot={"version": 77})
    assert not parsed.calls
    assert result["report"]["research"]["termination_reason"] == "snapshot_invalid"


@pytest.mark.asyncio
async def test_role_selects_tool_then_finishes_and_invalid_citation_is_degraded(monkeypatch):
    global parsed
    parsed = ParsedResponses([
        SupervisorDecision(action="dispatch", reason="claim needs evidence", assignments=[
            {"role": "claims", "question": "claim"}
        ]),
        RoleAction(action="search_official", query="approved claim"),
        RoleAction(action="finish", result=RoleResult(role="claims", status="completed", question="claim",
            findings=[{"statement": "Supported claim", "status": "supported", "source_ids": ["made-up"],
                       "quotes": [{"source_id": "made-up", "excerpt": "invented"}],
                       "applicability": "product_applicable"}])),
        SupervisorDecision(action="finish", reason="no other role needed"),
    ])

    class StubTools:
        def __init__(self, settings, reserve, *, owner):
            self.reserve, self.owner = reserve, owner

        async def search_official(self, query):
            assert query == "approved claim"
            assert self.reserve(self.owner, 10)
            return []

    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    monkeypatch.setattr("supplement_advisor.agents.research_graph.EvidenceTools", StubTools)
    result = await run_research_graph({"product": {}, "claims": ["claim"]}, config())
    claims = next(row for row in result["report"]["research"]["roles"] if row["role"] == "claims")
    assert len(parsed.calls) == 4
    assert claims["status"] == "insufficient_evidence"
    assert claims["findings"][0]["status"] == "not_assessable"


@pytest.mark.asyncio
async def test_total_budget_reservation_prevents_extra_model_calls(monkeypatch):
    global parsed
    parsed = ParsedResponses([
        SupervisorDecision(action="dispatch", reason="claims need check", assignments=[
            {"role": "claims", "question": "claim"}
        ]),
    ])
    reservations = []
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}}, config(max_tool_calls=1,
        reserve_budget=lambda **kw: reservations.append(kw) or True))
    assert len(parsed.calls) == 1
    assert len(reservations) == 1
    assert result["snapshot"]["counters"]["total"] == 1
    assert result["report"]["research"]["status"] == "partial"


@pytest.mark.asyncio
async def test_unknown_inflight_action_is_not_replayed(monkeypatch):
    global parsed
    parsed = ParsedResponses([])
    collection = {"product": {}}
    snapshot = {
        "version": 1, "fingerprint": __import__("supplement_advisor.agents.research_graph", fromlist=["_fingerprint"])._fingerprint(collection),
        "collection": collection, "collection_tool_calls": 0, "phase": "roles", "roles": {},
        "sources": [], "decisions": [], "counters": {"total": 1, "by_owner": {"claims": 1},
        "redirect_total": 0, "redirect_by_role": {}, "retry_total": 0},
        "in_flight": {"claims": {"kind": "model", "sequence": 1, "action": "role_action"}},
        "termination_reason": None,
    }
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph(collection, config(initial_tool_calls=1), snapshot=snapshot)
    assert not parsed.calls
    assert result["report"]["research"]["termination_reason"] == "unknown_interrupted"


@pytest.mark.asyncio
async def test_window_without_timeout_plus_save_margin_yields_without_request(monkeypatch):
    global parsed
    parsed = ParsedResponses([])
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}}, config(), remaining_seconds=1.5)
    assert not parsed.calls
    assert result["yielded"] is True
    assert result["snapshot"]["termination_reason"] == "window_exhausted"
    assert result["snapshot"]["phase"] == "supervisor"
    assert "report" not in result["snapshot"]


@pytest.mark.asyncio
async def test_snapshot_budget_mismatch_and_checkpoint_lease_loss_fail_closed(monkeypatch):
    global parsed
    parsed = ParsedResponses([])
    collection = {"product": {}}
    from supplement_advisor.agents.research_graph import _fingerprint
    mismatched = {"version": 1, "fingerprint": _fingerprint(collection), "collection": collection,
        "collection_tool_calls": 0, "phase": "supervisor", "roles": {}, "sources": [], "decisions": [],
        "counters": {"total": 2, "by_owner": {"claims": 1}, "redirect_total": 0,
                     "redirect_by_role": {}, "retry_total": 0}, "in_flight": {}, "termination_reason": None}
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    mismatch_result = await run_research_graph(collection, config(initial_tool_calls=1), snapshot=mismatched)
    assert mismatch_result["report"]["research"]["termination_reason"] == "budget_state_mismatch"
    assert not parsed.calls

    result = await run_research_graph(collection, config(), checkpoint=lambda snap: False)
    assert not parsed.calls
    assert result["report"]["research"]["termination_reason"] == "lease_lost"


@pytest.mark.asyncio
async def test_role_call_cap_is_six_including_each_retry(monkeypatch):
    global parsed
    parsed = ParsedResponses([
        SupervisorDecision(action="dispatch", reason="claims", assignments=[
            {"role": "claims", "question": "claim"}
        ]),
    ] + [RoleAction(action="search_official", query="claim") for _ in range(6)])
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}}, config(max_tool_calls=20))
    assert result["snapshot"]["counters"]["by_owner"].get("claims", 0) == 6
    assert result["snapshot"]["roles"]["claims"]["reasons"] == ["budget_exhausted"]


@pytest.mark.asyncio
async def test_supervisor_redirect_is_limited_to_one_per_role(monkeypatch):
    global parsed
    assign_claims = SupervisorDecision(action="dispatch", reason="claim", assignments=[
        {"role": "claims", "question": "claim"}
    ])
    finish_claims = RoleAction(action="finish", result=finding_result("claims"))
    parsed = ParsedResponses([assign_claims, finish_claims, assign_claims, finish_claims, assign_claims])
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}}, config())
    assert len(parsed.calls) == 5
    assert result["snapshot"]["counters"]["redirect_total"] == 1
    assert result["report"]["research"]["termination_reason"] == "redirect_limit"
    assert result["snapshot"]["in_flight"] == {}


@pytest.mark.asyncio
async def test_transient_model_failure_retries_once_with_a_new_reservation(monkeypatch):
    global parsed
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))

    class RetryResponses(ParsedResponses):
        async def parse(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 2:
                raise RateLimitError("throttled", response=response, body=None)
            if len(self.calls) == 3:
                return SimpleNamespace(output_parsed=RoleAction(
                    action="finish", result=finding_result("claims")), status="completed")
            return SimpleNamespace(output_parsed=SupervisorDecision(
                action="dispatch" if len(self.calls) == 1 else "finish",
                reason="claim check" if len(self.calls) == 1 else "done",
                assignments=[{"role": "claims", "question": "claim"}] if len(self.calls) == 1 else []),
                status="completed")

    parsed = RetryResponses([])
    reservations = []
    saved = []
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}}, config(
        reserve_budget=lambda **kw: reservations.append(kw) or True,
        save_snapshot=lambda snapshot: saved.append(snapshot) or True))
    assert len(parsed.calls) == 4
    assert len(reservations) == 4
    assert result["snapshot"]["counters"]["retry_total"] == 1
    assert result["snapshot"]["roles"]["claims"]["retry_used"] is True
    committed = [snapshot for snapshot in saved
                 if snapshot["roles"].get("claims", {}).get("finished")]
    assert committed
    assert all("claims" not in snapshot["in_flight"] for snapshot in committed)


@pytest.mark.asyncio
async def test_three_selected_roles_run_concurrently_but_not_more(monkeypatch):
    from supplement_advisor.agents.research_types import Assignment, RoleAction

    active = 0
    maximum = 0

    class ConcurrentResponses:
        def __init__(self):
            self.calls = []
            self.first_supervisor = True

        async def parse(self, **kwargs):
            nonlocal active, maximum
            self.calls.append(kwargs)
            if kwargs["text_format"] is SupervisorDecision:
                if self.first_supervisor:
                    self.first_supervisor = False
                    return SimpleNamespace(output_parsed=SupervisorDecision(action="dispatch",
                        reason="parallel", assignments=[
                            Assignment(role="claims", question="claim"),
                            Assignment(role="safety", question="safety"),
                            Assignment(role="composition", question="label"),
                        ]), status="completed")
                return SimpleNamespace(output_parsed=SupervisorDecision(action="finish",
                    reason="complete"), status="completed")
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            role = json.loads(kwargs["input"][1]["content"])["role"]
            active -= 1
            return SimpleNamespace(output_parsed=RoleAction(
                action="finish", result=finding_result(role)), status="completed")

    global parsed
    parsed = ConcurrentResponses()
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    await run_research_graph({"product": {}}, config())
    assert maximum == 3


@pytest.mark.asyncio
async def test_transient_tool_failure_retries_once_through_a_fresh_reservation(monkeypatch):
    from supplement_advisor.agents.evidence_tools import ResearchToolError

    global parsed
    parsed = ParsedResponses([
        SupervisorDecision(action="dispatch", reason="claim check", assignments=[
            {"role": "claims", "question": "claim"}
        ]),
        RoleAction(action="search_official", query="claim"),
        RoleAction(action="finish", result=finding_result("claims")),
        SupervisorDecision(action="finish", reason="done"),
    ])

    class FlakyTools:
        def __init__(self, settings, reserve, *, owner):
            self.reserve, self.owner, self.attempts = reserve, owner, 0

        async def search_official(self, query):
            self.attempts += 1
            assert self.reserve(self.owner, 10)
            if self.attempts == 1:
                raise ResearchToolError("timeout")
            return []

    reservations = []
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    monkeypatch.setattr("supplement_advisor.agents.research_graph.EvidenceTools", FlakyTools)
    result = await run_research_graph({"product": {}}, config(
        reserve_budget=lambda **kw: reservations.append(kw) or True))
    assert len(parsed.calls) == 4
    assert len(reservations) == 6
    assert result["snapshot"]["counters"]["retry_total"] == 1
    assert result["snapshot"]["roles"]["claims"]["retry_used"] is True


@pytest.mark.asyncio
async def test_yielded_dispatch_resumes_without_repeating_supervisor(monkeypatch):
    from supplement_advisor.agents.research_graph import _fingerprint

    collection = {"product": {}}
    snapshot = {"version": 1, "fingerprint": _fingerprint(collection), "collection": collection,
        "collection_tool_calls": 0, "phase": "roles", "roles": {},
        "pending_assignments": [{"role": "claims", "question": "claim"}],
        "sources": [], "decisions": [{"action": "dispatch", "role": "supervisor", "reason": "claim"}],
        "counters": {"total": 1, "by_owner": {"supervisor": 1}, "redirect_total": 0,
            "redirect_by_role": {}, "retry_total": 0},
        "in_flight": {}, "termination_reason": "window_exhausted"}
    global parsed
    parsed = ParsedResponses([
        RoleAction(action="finish", result=finding_result("claims")),
        SupervisorDecision(action="finish", reason="done"),
    ])
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    resumed = await run_research_graph(collection, config(initial_tool_calls=1),
                                       snapshot=snapshot, remaining_seconds=60)
    assert resumed["yielded"] is False
    assert len(parsed.calls) == 2
    assert resumed["report"]["research"]["termination_reason"] is None


@pytest.mark.asyncio
async def test_resumed_pending_tool_action_runs_without_role_model_recall(monkeypatch):
    from supplement_advisor.agents.research_graph import _fingerprint

    collection = {"product": {}}
    snapshot = {"version": 1, "fingerprint": _fingerprint(collection), "collection": collection,
        "collection_tool_calls": 0, "phase": "roles",
        "roles": {"claims": {"question": "claim", "status": "running",
            "pending_action": RoleAction(action="search_official", query="claim").model_dump(),
            "result": None, "retry_used": False}},
        "pending_assignments": [{"role": "claims", "question": "claim"}],
        "sources": [], "decisions": [], "counters": {"total": 1, "by_owner": {"claims": 1},
            "redirect_total": 0, "redirect_by_role": {}, "retry_total": 0},
        "in_flight": {}, "termination_reason": None}
    global parsed
    parsed = ParsedResponses([SupervisorDecision(action="finish", reason="done")])

    class StubTools:
        def __init__(self, settings, reserve, *, owner):
            self.reserve, self.owner = reserve, owner

        async def search_official(self, query):
            assert query == "claim"
            assert self.reserve(self.owner, 10)
            return []

    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    monkeypatch.setattr("supplement_advisor.agents.research_graph.EvidenceTools", StubTools)
    result = await run_research_graph(collection, config(initial_tool_calls=1), snapshot=snapshot)
    assert len(parsed.calls) == 1
    assert result["snapshot"]["roles"]["claims"]["last_tool_result"]["action"] == "search_official"


@pytest.mark.asyncio
async def test_model_deadline_reservation_uses_full_model_timeout(monkeypatch):
    from supplement_advisor.agents.research_graph import _fingerprint

    global parsed
    parsed = ParsedResponses([])
    collection = {"product": {}}
    snapshot = {"version": 1, "fingerprint": _fingerprint(collection), "collection": collection,
        "collection_tool_calls": 0, "phase": "roles", "roles": {},
        "pending_assignments": [{"role": "claims", "question": "claim"}],
        "sources": [], "decisions": [{"action": "dispatch", "role": "supervisor", "reason": "claim"}],
        "counters": {"total": 1, "by_owner": {"supervisor": 1}, "redirect_total": 0,
            "redirect_by_role": {}, "retry_total": 0},
        "in_flight": {}, "termination_reason": None}
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph(collection, config(initial_tool_calls=1), snapshot=snapshot,
                                      remaining_seconds=20)
    assert not parsed.calls
    assert result["yielded"] is True, result["snapshot"].get("termination_reason")
    assert result["snapshot"]["termination_reason"] == "window_exhausted"


@pytest.mark.asyncio
async def test_tool_result_and_marker_removal_are_saved_atomically(monkeypatch):
    from supplement_advisor.agents.research_types import ResearchSource

    global parsed
    parsed = ParsedResponses([
        SupervisorDecision(action="dispatch", reason="claims", assignments=[
            {"role": "claims", "question": "claim"}
        ]),
        RoleAction(action="search_official", query="claim"),
        RoleAction(action="finish", result=finding_result("claims")),
        SupervisorDecision(action="finish", reason="done"),
    ])
    saved = []

    class StubTools:
        def __init__(self, settings, reserve, *, owner):
            self.reserve, self.owner = reserve, owner

        async def search_official(self, query):
            assert self.reserve(self.owner, 10)
            return [ResearchSource(id="source-1", kind="official", title="Official", url="https://mfds.go.kr/a",
                retrieved_at="2026-11-11T00:00:00Z", provider="test", access_scope="document",
                excerpt="text", text="text")]

    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    monkeypatch.setattr("supplement_advisor.agents.research_graph.EvidenceTools", StubTools)
    await run_research_graph({"product": {}}, config(save_snapshot=lambda value: saved.append(value) or True))
    action_states = [snap for snap in saved if snap.get("roles", {}).get("claims", {}).get("last_tool_result", {}).get("action") == "search_official"]
    assert action_states
    assert any(any(source["id"] == "source-1" for source in snap["sources"])
               and "claims" not in snap["in_flight"] for snap in action_states)
    assert not any(not any(source["id"] == "source-1" for source in snap["sources"])
                   and "claims" not in snap["in_flight"] for snap in action_states)


@pytest.mark.asyncio
async def test_lease_loss_latches_all_later_reservations(monkeypatch):
    global parsed
    parsed = ParsedResponses([
        SupervisorDecision(action="dispatch", reason="parallel", assignments=[
            {"role": "claims", "question": "claim"},
            {"role": "safety", "question": "safety"},
            {"role": "composition", "question": "label"},
        ]),
    ] + [RoleAction(action="finish", result=finding_result(role))
         for role in ("claims", "safety", "composition")])
    reservations = []
    save_calls = 0

    def checkpoint(snapshot):
        nonlocal save_calls
        save_calls += 1
        return save_calls != 3

    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}}, config(
        reserve_budget=lambda **kw: reservations.append(kw) or True), checkpoint=checkpoint)
    assert len(reservations) == 2
    assert len(parsed.calls) == 1
    assert result["report"]["research"]["termination_reason"] == "lease_lost"


def test_model_output_schemas_publish_exact_role_tool_and_finding_enums():
    role_schema = RoleAction.model_json_schema()
    supervisor_schema = SupervisorDecision.model_json_schema()
    assert role_schema["properties"]["action"]["enum"] == [
        "search_official", "search_literature", "fetch_source", "finish"
    ]
    role_result = role_schema["$defs"]["RoleResult"]
    assert role_result["properties"]["role"]["enum"] == [
        "composition", "claims", "personal_fit", "safety", "official_quality"
    ]
    assert role_result["properties"]["status"]["enum"] == [
        "completed", "partial", "insufficient_evidence", "not_applicable", "unavailable", "failed"
    ]
    finding = role_schema["$defs"]["Finding"]
    assert finding["properties"]["status"]["enum"] == [
        "supported", "contradicted", "mixed", "not_assessable"
    ]
    assert finding["properties"]["applicability"]["enum"] == [
        "ingredient_only", "product_label", "product_applicable", "unassessed"
    ]
    assert supervisor_schema["properties"]["action"]["enum"] == ["dispatch", "finish"]
    assert supervisor_schema["$defs"]["Assignment"]["properties"]["role"]["enum"] == [
        "composition", "claims", "safety", "official_quality"
    ]


@pytest.mark.asyncio
async def test_actual_model_calls_receive_catalogued_schema_and_role_tool_prompts(monkeypatch):
    global parsed
    parsed = ParsedResponses([
        SupervisorDecision(action="dispatch", reason="check claims", assignments=[
            {"role": "claims", "question": "claim support"}
        ]),
        RoleAction(action="finish", result=finding_result("claims")),
        SupervisorDecision(action="finish", reason="done"),
    ])
    monkeypatch.setattr("supplement_advisor.agents.research_graph.AsyncOpenAI", Client, raising=False)
    result = await run_research_graph({"product": {}, "claims": ["claim"]}, config())
    supervisor_input = parsed.calls[0]["input"][0]["content"]
    role_input = parsed.calls[1]["input"][0]["content"]
    assert "composition" in supervisor_input and "official_quality" in supervisor_input
    assert "personal_fit" in supervisor_input and "배정하지" in supervisor_input
    assert "search_official(query)" in role_input
    assert "search_literature(query)" in role_input
    assert "fetch_source(등록 source_id)" in role_input
    assert "finish(result)" in role_input
    assert "ingredient_only" in role_input and "product_applicable" in role_input
    assert parsed.calls[0]["text_format"] is SupervisorDecision
    assert parsed.calls[1]["text_format"] is RoleAction
    assert result["report"]["research"]["status"] == "completed"
