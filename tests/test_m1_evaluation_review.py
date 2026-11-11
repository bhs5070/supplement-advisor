"""Independent contract checks for the frozen M1 evaluation harness."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import evaluate_m1 as evaluation

CORPUS = Path(__file__).parents[1] / "docs/evaluation/m1-corpus.json"
ANNOTATED_CORPUS = Path(__file__).parents[1] / "docs/evaluation/m1-corpus-annotated-v2.json"


def _frozen_manifest():
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _report():
    return {
        "product": {"name": "Vitamin C", "manufacturer": None, "report_number": None},
        "claims": [],
        "ingredients": [],
        "extraction_status": {"code": "success"},
        "official_match": {"state": "unknown", "evidence": [], "reasons": []},
    }


def test_actual_frozen_corpus_is_valid_and_has_expected_fixed_shape():
    manifest = evaluation.validate_manifest(_frozen_manifest())
    assert len(manifest["samples"]) == 20
    assert 3 <= len(manifest["sites"]) <= 5
    assert len({item["id"] for item in manifest["samples"]}) == 20
    assert len({item["url"] for item in manifest["samples"]}) == 20


def test_annotated_v2_preserves_same_frozen_urls_and_has_valid_label_denominators():
    original = _frozen_manifest()
    manifest = json.loads(ANNOTATED_CORPUS.read_text(encoding="utf-8"))
    evaluation.validate_manifest(manifest)
    assert manifest["parent_manifest_sha256"] == hashlib.sha256(CORPUS.read_bytes()).hexdigest()
    assert [sample["url"] for sample in manifest["samples"]] == [sample["url"] for sample in original["samples"]]
    assert len(manifest["samples"]) == 20
    for field in ("product_name", "manufacturer", "report_number"):
        assert sum(
            sample["labels"]["identity"][field]["status"] == "known"
            for sample in manifest["samples"]
        ) > 0
    assert sum(
        sample["labels"]["identity"]["report_number"]["status"] == "not_in_page"
        for sample in manifest["samples"]
    ) == 15


def test_frozen_identity_label_shape_is_scored_with_correct_field_mapping():
    sample = {
        "labels": {
            "identity": {
                "product_name": {"status": "known", "values": ["Vitamin C"]},
                "manufacturer": {"status": "unknown", "values": []},
                "report_number": {"status": "not_in_page", "values": []},
            },
            "official_registration": {"status": "known", "report_numbers": ["123"]},
        }
    }
    report = _report()
    report["official_match"] = {
        "state": "matched",
        "matched_record": {"PRDLST_REPORT_NO": "999"},
        "evidence": [],
    }
    assessment = evaluation._assess_labels(sample, report)
    assert assessment["name"]["status"] == "correct"
    assert assessment["manufacturer"]["status"] == "unjudged"
    assert assessment["report_number"]["status"] == "unjudged"
    assert assessment["official_match"]["status"] == "false_match"


def test_unknown_official_label_never_becomes_false_match():
    sample = {"labels": {"official_registration": {"status": "unknown", "report_numbers": []}}}
    report = _report()
    report["official_match"] = {"state": "matched", "matched_record": {"PRDLST_REPORT_NO": "x"}}
    assert evaluation._assess_labels(sample, report)["official_match"]["status"] == "unjudged"


def test_known_official_label_with_candidate_is_counted_as_not_confirmed():
    sample = {"labels": {"official_registration": {"status": "known", "report_numbers": ["123"]}}}
    report = _report()
    report["official_match"] = {"state": "candidate", "reasons": ["ambiguous"]}
    assert evaluation._assess_labels(sample, report)["official_match"]["status"] == "not_confirmed"


def test_report_number_evidence_cannot_override_wrong_matched_record():
    sample = {"labels": {"official_registration": {"status": "known", "report_numbers": ["123"]}}}
    report = _report()
    report["official_match"] = {
        "state": "matched",
        "matched_record": {"PRDLST_REPORT_NO": "999"},
        "evidence": [{"field": "report_number", "official_value": "123"}],
    }
    assert evaluation._assess_labels(sample, report)["official_match"]["status"] == "false_match"


def test_known_labels_require_nonempty_expected_values():
    manifest = _frozen_manifest()
    labels = manifest["samples"][0]["labels"]
    identity = labels.get("identity", labels)
    product_name = identity.get("product_name", identity.get("name"))
    assert product_name is not None
    product_name["status"] = "known"
    product_name["values"] = []
    with pytest.raises(evaluation.ManifestError, match="identity_label_invalid"):
        evaluation.validate_manifest(manifest)


def test_identity_summary_preserves_known_unknown_and_not_in_page_label_denominators():
    samples = [
        {"identity": {"name": {"status": "correct", "label_status": "known"}}},
        {"identity": {"name": {"status": "unjudged", "label_status": "unknown"}}},
        {"identity": {"name": {"status": "unjudged", "label_status": "not_in_page"}}},
    ]
    summary = evaluation._summary(samples)
    name = summary["identity"]["name"]
    assert name["label_status"] == {"known": 1, "unknown": 1, "not_in_page": 1}
    assert name["outcome"] == {"correct": 1, "unjudged": 2}


def test_official_summary_preserves_known_vs_unknown_label_denominator():
    samples = [
        {"identity": {"official_match": {"status": "true_match", "label_status": "known"}}},
        {"identity": {"official_match": {"status": "unjudged", "label_status": "unknown"}}},
    ]
    summary = evaluation._summary(samples)
    assert summary["official_judgement"]["label_status"] == {"known": 1, "unknown": 1}
    assert summary["official_judgement"]["outcome"] == {"true_match": 1, "unjudged": 1}


@pytest.mark.parametrize(
    ("report_number", "expected"),
    [(None, "expected_missing"), ("999", "unexpected_present")],
)
def test_not_in_page_label_checks_expected_absence_only_after_successful_extraction(report_number, expected):
    sample = {
        "labels": {
            "identity": {
                "report_number": {"status": "not_in_page", "values": []},
            }
        }
    }
    report = _report()
    report["extraction_status"] = {"code": "extracted"}
    report["product"]["report_number"] = report_number
    assert evaluation._assess_labels(sample, report)["report_number"]["status"] == expected


def test_not_in_page_label_stays_unjudged_when_extraction_did_not_complete():
    sample = {
        "labels": {
            "identity": {
                "report_number": {"status": "not_in_page", "values": []},
            }
        }
    }
    report = _report()
    report["extraction_status"] = {"code": "request_failed"}
    assert evaluation._assess_labels(sample, report)["report_number"] == {
        "status": "unjudged",
        "label_status": "not_in_page",
        "reason": "extraction_not_completed",
    }


def test_execution_signature_inputs_are_safe_and_include_extraction_code_hash():
    settings = SimpleNamespace(
        openai_model="gpt-5.6-luna",
        external_timeout_seconds=15,
        model_timeout_seconds=15,
        analysis_timeout_seconds=180,
        attempt_timeout_seconds=60,
        max_tool_calls=20,
        openai_api_key="secret-openai-key",
        food_safety_api_key="secret-official-key",
        auth_token="secret-token",
    )
    config = evaluation._safe_execution_config(settings)
    assert config == {
        "openai_model": "gpt-5.6-luna",
        "external_timeout_seconds": 15,
        "model_timeout_seconds": 15,
        "analysis_timeout_seconds": 180,
        "attempt_timeout_seconds": 60,
        "max_tool_calls": 20,
    }
    assert all("secret" not in value for value in config.values() if isinstance(value, str))
    assert "structured_extraction" in evaluation._code_hashes()


def test_invalid_manifest_fails_before_any_collection(tmp_path, monkeypatch):
    manifest = _frozen_manifest()
    manifest["samples"][0]["url"] = "https://attacker.example/item"
    manifest_path = tmp_path / "invalid.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(evaluation, "collect_page", lambda url: pytest.fail("external collection started"))

    with pytest.raises(evaluation.ManifestError, match="sample_host_does_not_match_site"):
        import asyncio

        asyncio.run(evaluation.evaluate(manifest_path, tmp_path / "out.json", use_configured_keys=False))


@pytest.mark.asyncio
async def test_collect_only_sample_runs_without_model_or_official_credentials(tmp_path, monkeypatch):
    manifest = _frozen_manifest()
    manifest["samples"][0]["labels"]["identity"]["product_name"] = {
        "status": "known",
        "values": ["DO_NOT_INJECT_LABEL"],
    }
    manifest["samples"][0]["cohort"] = "DO_NOT_INJECT_COHORT"
    manifest["samples"][0]["expected_display_name"] = "DO_NOT_INJECT_DISPLAY_NAME"
    manifest["samples"][0]["discovery_url"] = "https://discovery.example/DO_NOT_INJECT"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        evaluation,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="secret-model-key",
            food_safety_api_key="secret-official-key",
            model_copy=lambda update: SimpleNamespace(**update),
        ),
    )

    async def collect(url):
        return SimpleNamespace(url=url, title="Page", html="<html>Vitamin C</html>", text="Vitamin C", images=[])

    async def graph(page, name, settings):
        assert name is None
        assert "DO_NOT_INJECT" not in page.text
        assert "DO_NOT_INJECT" not in page.html
        assert settings.openai_api_key is None
        assert settings.food_safety_api_key is None
        assert page.text == "Vitamin C"
        return _report()

    monkeypatch.setattr(evaluation, "collect_page", collect)
    monkeypatch.setattr(evaluation, "run_collection_graph", graph)
    output_path = tmp_path / "result.json"
    result = await evaluation.evaluate(manifest_path, output_path, use_configured_keys=False)
    assert result["denominators"]["manifest_n"] == 20
    assert result["mode"] == "collect_only"
    assert all(sample["status"] == "completed" for sample in result["samples"])
    serialized = output_path.read_text(encoding="utf-8")
    assert "secret-model-key" not in serialized
    assert "secret-official-key" not in serialized


@pytest.mark.asyncio
async def test_completed_checkpoint_resume_does_not_repeat_collection_or_analysis(tmp_path, monkeypatch):
    manifest = _frozen_manifest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")
    calls = {"collect": 0, "analysis": 0}
    monkeypatch.setattr(evaluation, "get_settings", lambda: SimpleNamespace(model_copy=lambda update: SimpleNamespace(**update)))

    async def collect(url):
        calls["collect"] += 1
        return SimpleNamespace(url=url, title="Page", html="<html/>", text="", images=[])

    async def graph(page, name, settings):
        calls["analysis"] += 1
        return _report()

    monkeypatch.setattr(evaluation, "collect_page", collect)
    monkeypatch.setattr(evaluation, "run_collection_graph", graph)
    output_path = tmp_path / "result.json"
    await evaluation.evaluate(manifest_path, output_path, use_configured_keys=False)
    first_counts = calls.copy()
    resumed = await evaluation.evaluate(manifest_path, output_path, use_configured_keys=False)
    assert calls == first_counts
    assert len(resumed["samples"]) == 20


@pytest.mark.asyncio
async def test_execution_config_change_rejects_resume_without_revealing_secrets(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_frozen_manifest()), encoding="utf-8")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")
    settings_state = {"model_timeout_seconds": 15}

    def settings():
        return SimpleNamespace(
            openai_api_key="secret-model-key",
            food_safety_api_key="secret-official-key",
            openai_model="gpt-5.6-luna",
            external_timeout_seconds=15,
            model_timeout_seconds=settings_state["model_timeout_seconds"],
            analysis_timeout_seconds=180,
            attempt_timeout_seconds=60,
            max_tool_calls=20,
            model_copy=lambda update: SimpleNamespace(
                **{
                    "openai_api_key": None,
                    "food_safety_api_key": None,
                    "openai_model": "gpt-5.6-luna",
                    "external_timeout_seconds": 15,
                    "model_timeout_seconds": settings_state["model_timeout_seconds"],
                    "analysis_timeout_seconds": 180,
                    "attempt_timeout_seconds": 60,
                    "max_tool_calls": 20,
                }
            ),
        )

    monkeypatch.setattr(evaluation, "get_settings", settings)
    calls = 0

    async def collect(url):
        nonlocal calls
        calls += 1
        return SimpleNamespace(url=url, title="Page", html="<html/>", text="", images=[])

    async def graph(page, name, runtime_settings):
        return _report()

    monkeypatch.setattr(evaluation, "collect_page", collect)
    monkeypatch.setattr(evaluation, "run_collection_graph", graph)
    output_path = tmp_path / "result.json"
    await evaluation.evaluate(manifest_path, output_path, use_configured_keys=False)
    prior_calls = calls
    prior_output = output_path.read_text(encoding="utf-8")
    assert "secret-model-key" not in prior_output
    assert "secret-official-key" not in prior_output
    assert json.loads(prior_output)["code_sha256"] == evaluation._code_hashes()["harness"]

    settings_state["model_timeout_seconds"] = 10
    with pytest.raises(evaluation.ManifestError, match="checkpoint_signature_mismatch"):
        await evaluation.evaluate(manifest_path, output_path, use_configured_keys=False)
    assert calls == prior_calls
    assert output_path.read_text(encoding="utf-8") == prior_output


@pytest.mark.asyncio
async def test_completed_result_keeps_report_and_frozen_cohort_metadata(tmp_path, monkeypatch):
    manifest = _frozen_manifest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(evaluation, "get_settings", lambda: SimpleNamespace(model_copy=lambda update: SimpleNamespace(**update)))

    async def collect(url):
        return SimpleNamespace(url=url, title="Page", html="<html/>", text="", images=[])

    async def graph(page, name, settings):
        return _report()

    monkeypatch.setattr(evaluation, "collect_page", collect)
    monkeypatch.setattr(evaluation, "run_collection_graph", graph)
    result = await evaluation.evaluate(manifest_path, tmp_path / "result.json", use_configured_keys=False)
    first = result["samples"][0]
    source = manifest["samples"][0]
    assert first["report"] == _report()
    assert first["cohort"] == source["cohort"]
    assert first["discovery_url"] == evaluation._safe_url(source["discovery_url"])


@pytest.mark.asyncio
async def test_checkpoint_mode_mismatch_is_rejected_without_collection(tmp_path, monkeypatch):
    manifest = _frozen_manifest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output_path = tmp_path / "result.json"
    output_path.write_text(json.dumps({"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "mode": "collect_only", "samples": []}), encoding="utf-8")

    async def collect(url):
        pytest.fail("mismatched checkpoint must fail before any request")

    monkeypatch.setattr(evaluation, "collect_page", collect)
    with pytest.raises((evaluation.ManifestError, ValueError)):
        await evaluation.evaluate(manifest_path, output_path, use_configured_keys=True)


@pytest.mark.asyncio
async def test_interrupted_sample_checkpoint_is_never_retried(tmp_path, monkeypatch):
    manifest = _frozen_manifest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(evaluation, "get_settings", lambda: SimpleNamespace(model_copy=lambda update: SimpleNamespace(**update)))
    calls = 0

    first_url = manifest["samples"][0]["url"]
    collected = []

    async def collect(url):
        nonlocal calls
        calls += 1
        collected.append(url)
        if url == first_url:
            raise KeyboardInterrupt
        return SimpleNamespace(url=url, title="Page", html="<html/>", text="", images=[])

    async def graph(page, name, settings):
        return _report()

    monkeypatch.setattr(evaluation, "collect_page", collect)
    monkeypatch.setattr(evaluation, "run_collection_graph", graph)
    output_path = tmp_path / "result.json"
    with pytest.raises(KeyboardInterrupt):
        await evaluation.evaluate(manifest_path, output_path, use_configured_keys=False)
    checkpoint = json.loads(output_path.read_text(encoding="utf-8"))
    assert checkpoint["samples"][0]["status"] == "started"
    resumed = await evaluation.evaluate(manifest_path, output_path, use_configured_keys=False)
    assert resumed["samples"][0]["status"] == "unknown_interrupted"
    assert collected.count(first_url) == 1

