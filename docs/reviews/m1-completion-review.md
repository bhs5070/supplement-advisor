# M1 completion independent review

Date: 2026-11-09  
Reviewer: independent QA  
Scope: `scripts/verify_product_quality.py`, `tests/test_product_quality_harness.py`, `scripts/verify_process_recovery.py`, `scripts/recovery_test_bootstrap.py`, `compose.recovery-test.yaml`, `tests/test_process_recovery_harness.py`, `README.md`, `AGENTS.md`, with `docs/contracts.md` and `docs/verification.md` as the governing contract.

## Result

No required findings in the reviewed changes. The product quality runner defaults to explicitly clearing configured API keys, reports the no-key mode, only enables external calls with `--use-configured-keys`, sanitizes custom URL userinfo/query/fragment before reporting, and degrades malformed ports safely. Report checks distinguish empty/unavailable extraction from successful grounded extraction, and constrain the M1 collection-only scope (`score: null`, `verdict: hold`). The default NOW/Solgar pages are described as a small US vendor sample, without claiming Korean I0030 matching or broad product quality.

The recovery harness uses a separate Compose project, DB/Redis volumes, and worker/beat services; its test fixture does not configure external API keys. It asserts the persisted 30-second reservation before both injected failure scenarios, checks the 240-second lease in the real child-kill scenario, waits for retry/fencing and the cumulative 60-second/two-call reservation, and separately exercises a synchronous operation that ignores Celery's 29-second soft limit until the 30-second hard limit. The integration test is explicitly marked and has a 900-second cap. README/docs distinguish actual integrations from mock and contract evidence.

## Verification executed

- `.venv/bin/python -m pytest tests/test_product_quality_harness.py tests/test_process_recovery_harness.py -q -m 'not integration'` — **9 passed, 1 deselected**. This deliberately excludes the long real-infrastructure integration test; that test was not duplicated while the separate recovery run was in progress.
- A first attempt with system `python -m pytest ...` terminated in a Python 3.13 `rlcompleter`/`pdb` segmentation fault during pytest initialization, before tests ran. Retrying with the project `.venv` succeeded.
- No paid external API call was made. No recovery integration scenario was run as part of this review.

## Review snapshot hashes

SHA-256 at review time:

| File | SHA-256 |
|---|---|
| `scripts/verify_product_quality.py` | `0225a3b47d468035efd508bcd41f31944159e3f248cf03aa91d8bdabd5d2f050` |
| `tests/test_product_quality_harness.py` | `60da8720e95cfbedeac841d1cc8acfe5c84ae45cf2abed8288d21262a90a1c99` |
| `scripts/verify_process_recovery.py` | `abb7c2c3516ce06924832cdf779adc9451dd2840a700f8f9415b969886c0fb32` |
| `scripts/recovery_test_bootstrap.py` | `160b712639340a60258f9a81ec33ba58b9bda8c0e7132f556b5422970c8e837c` |
| `compose.recovery-test.yaml` | `0fc39623255b027f44503573f68999cb5b71a8df1e66fc118742529f45615bd4` |
| `tests/test_process_recovery_harness.py` | `d152b6143848c3c897ea19c7c7334ed57a4d7ddcbbffd4ec39f1cd782a1b93bf` |
| `README.md` | `69c4d04d2e5affe0a5f0636f4fb1182cb6fb684d44941ac2d8147cae51d2b422` |
| `AGENTS.md` | `338830ef29cca0139ca18e5b52bcd855aea2e89b01e2da5d04e131eba23768f0` |

## Limits

Live NOW/Solgar collection and any model/API-backed extraction were not run in this review. Successful external service authentication, model extraction quality, official product matching, and the real prefork kill/hard-timeout outcome remain dependent on the separate run's captured evidence. The unit test result is not evidence of those live outcomes.

## Follow-up evidence review — recovery run

The lead supplied `work/verification/2026-11-09-process-recovery.log` after the initial review. This is the author's separate execution evidence; it is not an integration run performed by the independent reviewer.

- Logged command: `.venv/bin/python scripts/verify_process_recovery.py`; exit 0, empty stderr.
- Both `kill` and `timeout` scenarios ended at `attempts=2`, `reserved_seconds=60`, `reserved_tool_calls=2`, `stale_finish=False`, `final_status=needs_input`.
- The log records a real prefork child SIGKILL, retry, and stale-token fencing. It also records the default 240-second lease expiring naturally in both scenarios; no forced expiry was used.
- The timeout scenario records the synchronous fixture ignoring Celery's 29-second soft limit and being stopped by the 30-second hard limit, followed by the retry.
- The log states both isolated Compose projects were brought down without `-v` (named volumes retained), while the existing application services remained up and DB/Redis healthy. The fixture intercepted URLs; no external product URL or service was contacted.

I reviewed the current recovery harness and README additions against that evidence. README gives both direct runner and explicitly gated pytest commands, explains the roughly ten-minute lease wait, and correctly says the test stack stops without deleting its volumes. The test gate (`RUN_PROCESS_RECOVERY=1`) matches the documented invocation. No required finding from this follow-up.

The recovery runner, integration test, and README changed after the first review, so the earlier hash table is only the initial review snapshot. Current hashes after this evidence review are:

| File | SHA-256 |
|---|---|
| `scripts/verify_product_quality.py` | `0225a3b47d468035efd508bcd41f31944159e3f248cf03aa91d8bdabd5d2f050` |
| `tests/test_product_quality_harness.py` | `60da8720e95cfbedeac841d1cc8acfe5c84ae45cf2abed8288d21262a90a1c99` |
| `scripts/verify_process_recovery.py` | `e494b1ae4420ea9cbef19f2d15eaf7de0d092e958df3ecdc1d333a9b7134e76a` |
| `scripts/recovery_test_bootstrap.py` | `160b712639340a60258f9a81ec33ba58b9bda8c0e7132f556b5422970c8e837c` |
| `compose.recovery-test.yaml` | `0fc39623255b027f44503573f68999cb5b71a8df1e66fc118742529f45615bd4` |
| `tests/test_process_recovery_harness.py` | `ff74a8393d2da6c8f87cf7378a01a32f5fef352d9f8c65b4fcd5eb4894caf191` |
| `README.md` | `fe5a988e9be145166a44de16077a9d7af4fd3ae461bc78e6672b26f6d65c31d5` |
| `AGENTS.md` | `338830ef29cca0139ca18e5b52bcd855aea2e89b01e2da5d04e131eba23768f0` |

No further test, recovery scenario, or external API call was run for this follow-up.

## Follow-up evidence review — configured live-stack product E2E

The lead supplied `work/verification/2026-11-09-configured-live-stack.json` after the prior reviews. This is the lead's live-stack execution artifact; I did not independently issue a product request or API call. The artifact's SHA-256 is `26a3e222248285006e9e70e37cade37093c2b6f3deae1f47316a61ef1a4af039`.

The artifact records a result for the public Solgar Vitamin C 1000 mg Vegetable Capsules page with `scope=collection_only`, `status=needs_input`, `error_code=insufficient_information`, `missing_fields=[manufacturer]`, and a persisted result identifier. It contains four ingredient rows (only Vitamin C has a listed 1000 mg amount), eight extracted page claims, and one advertising source. The checks say page collection `verified`, displayed-information extraction `unverified`, official registration match `unverified`, and personal suitability `not_applicable`. The report keeps `score=null` and `verdict=hold`; its official-registration detail explicitly says failure to match is not evidence of non-registration or illegality. The artifact also records `unauthorized_access_status=404`.

The lead's execution notes report that the real POST traversed PostgreSQL, Redis/Celery, HTTPX, OpenAI, and FoodSafety lookup, followed by an authorized token read returning 200; the artifact supplies the resulting stored report and unauthorized 404 record. The lead reports two paid model calls total for the combined live checks (one synthetic and one product); the earlier NOW/tablets collection failure made zero model calls. These are the lead's execution facts, not independently reproduced by this reviewer. The artifact does not establish a positive official product match: manufacturer and report number are absent and the official check remains unverified. Thus it supports one successful public product collection/extraction example and persistence/access behavior, not Korean product identification coverage, broad extraction quality, or clinical/product efficacy.

No required finding from this artifact review. No paid API call or test was run for this follow-up.

## Follow-up code review — official lookup by report number

The lead supplied the FoodSafety diagnostics showing an exact product-name lookup returning zero rows for the supplied item while `PRDLST_REPORT_NO=20190009483739` returned one record with the matching product name, manufacturer, and report number. I reviewed these artifacts without making an API call:

- `work/verification/2026-11-09-food-safety-diagnostic.json` — SHA-256 `68999919840011bd124fff419e9e7dcd8cf0811e6bd6b771e3c891d7da4790c2`.
- `work/verification/2026-11-09-food-safety-number-filter.json` — SHA-256 `f8a892f73d57a501dd41eebc9b4d07c8961083ab94ef6c732acba02fd84088c0`.

The code now supplies a grounded report number to `_official_records`; when present, the request uses `PRDLST_REPORT_NO`, otherwise it retains the prior `PRDLST_NM` name search. In both cases the response is still accepted only when exactly one row matches all three normalized identity values (product name, manufacturer, report number). A partial/mismatched identity remains unverified. The request still uses the official HTTPS API transport, key URL-encoding, no environment proxy, bounded response size, and the existing call budget. Call-site review found only `_check_official` invokes `_official_records`; its optional keyword preserves name-only behavior for callers without report number. Tests cover number-filter selection, exact three-field confirmation, name-only non-match, and partial-identity non-match. I found no required false-positive or compatibility issue.

Independent checks run locally:

- `.venv/bin/python -m pytest tests/test_agents.py tests/test_review_regressions.py -q` — **24 passed**.
- `.venv/bin/ruff check src/supplement_advisor/agents/collection_graph.py tests/test_agents.py` — **All checks passed**.
- No live FoodSafety API request or paid model call was made in this review.

Current reviewed source hashes:

| File | SHA-256 |
|---|---|
| `src/supplement_advisor/agents/collection_graph.py` | `60c85a7cb98c97a09a77dcd36a8e71063fcd9c38e678d12a83dcc3a32b5cb147` |
| `tests/test_agents.py` | `8ce0d03f552b8d1461217046b36d1dca5cb224942dee24b40b9b46ae5a3357ad` |

No required finding. The live post-fix official lookup outcome remains for the lead to verify; these tests and the earlier diagnostics alone do not demonstrate that the changed product path now returns a positive match.

## Follow-up evidence review — post-fix controlled official lookup

The lead supplied `work/verification/2026-11-09-food-safety-matching-fixed.json`; SHA-256 `87733e825de6935e5674fdd57af767ca501d61002dfe787569c5f678cc2e4f88`. I reviewed the artifact without rerunning tests or making API calls.

It records two official API calls and zero model calls. Given a controlled identity copied from an authenticated official record (explicitly not extracted from the vendor page), the exact identity returned `verified` / `registration_matched` with product name, manufacturer, report number, and update date. A variant with a mismatched manufacturer returned `unverified` / `identity_not_confirmed` and no match. This is useful positive/negative evidence for the corrected report-number query and the three-field identity gate. It does not establish independent Korean product matching from a vendor sales page, because the test input already contains the official identity fields. The earlier real product-page result remains `official registration unverified` due to missing manufacturer/report number; the earlier name-search failure artifact remains preserved. No broader matching-accuracy claim follows from this controlled case.

No required finding. No additional verification or paid call was performed.
