# M1 evaluation harness independent review

Date: 2026-11-11  
Reviewed implementation: `scripts/evaluate_m1.py` SHA256 `4d4da3dece7b49f990e54c556153d235394b5e3332146868c7016a00767a0b6c`  
Frozen source manifest: `docs/evaluation/m1-corpus.json` SHA256 `a6abedfbbd84a46a569f717fe42e6e60348661c7717b3885b4fb9e556ec091af`  
Annotated stage 1 manifest: `docs/evaluation/m1-corpus-annotated-v2.json` SHA256 `d66c8c55d766c5850c14c505837d322be8565ad64e0965f2659b32a729a1853c`

## Scope and result

Independent QA reviewed the fixed 20 URL/5 site source manifest, its annotated v2 labels, and the evaluation harness using mocked collection and analysis functions only. No real URL, model, or official provider call was made by QA. Both manifests validate offline; v2 has the same 20 URLs and points back to the original manifest SHA256. V2 label denominators are product name 16 known / 4 unknown, manufacturer 5 known / 15 unknown, report number 1 known / 4 unknown / 15 `not_in_page`, and official registration 1 known / 19 unknown. The original cohorts are 4 regression seeds and 16 discovery holdouts; site counts are CKD 5, KGC 4, ER Hana 2, SSG 4, GS 5.

The core harness checks passed: opt-in credentials are cleared in collect-only mode, invalid site hosts are rejected before collection, model inputs contain only collected page content, unknown labels remain unjudged, official false matches require a known answer and the returned record number, and completed or interrupted samples are not requested twice. The output preserves report, cohort, discovery URL, and labels. Checkpoint signatures bind mode, manifest, harness/product code hashes, and a non-secret allowlist of model/runtime settings; only the harness began the run is reported as its code hash. API keys and auth tokens are excluded.

The required denominator issues found in earlier review iterations are resolved in the reviewed version. Each identity field reports label strata (`known`, `unknown`, `not_in_page`) separately from outcomes. Official-registration summaries likewise separate label strata from true/false/not-confirmed/unjudged outcomes. A report-number `not_in_page` label becomes `expected_missing` or `unexpected_present` only after extraction completes; extraction failures remain unjudged. Candidate or unverified official predictions for known labels are `not_confirmed`, not false matches. Do not interpret zero false matches as a safety result: v2 has only one known official-registration label and 19 unknowns.

## Verification evidence

- Final combined writer and independent suites: 31 passed (`tests/test_m1_evaluation.py` plus 19 independent review cases, including parameterized `not_in_page` cases).
- Ruff passed for the harness and both test files; CLI `--help` completed; `git diff --check` passed for the owned review artifacts.
- Independent tests cover frozen v1/v2 linkage and URL stability, label denominators, official false-match guard, `not_in_page` outcomes, checkpoint mode/config mismatch, interrupted resume, collect-only credential stripping, metadata isolation from model inputs, and source/config signature redaction.
- A pre-freeze iteration found that completion output omitted `discovery_url`; the writer fixed it before final review. No remaining required finding was observed in the final mock suite.

## Review disposition

**Harness QA disposition: passed for the reviewed code and mock scope.** The root-owned stage 1 run was later reviewed read-only in [m1-evaluation-adjudication.md](m1-evaluation-adjudication.md). That review preserves unknown gold labels and records any post-hoc source judgement separately from frozen annotations.

The corpus is a fixed convenience sample, not a representative random sample; any resulting rates apply only to this set and measured stage. The offline QA pass does not establish live collection or model quality.
