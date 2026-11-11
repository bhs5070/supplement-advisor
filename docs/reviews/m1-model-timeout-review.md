# M1 dedicated model timeout independent QA — 2026-11-10

Independent review of the writer-frozen timeout adjustment. Scope: `config.py`, collection `_extract`, and its snapshot behavior. No product code was changed by QA.

## Findings

The extraction request uses `model_timeout_seconds` (default 30 seconds, maximum 30), passes that value to both the SDK and the enclosing asyncio deadline, and reserves the same duration before starting the request. Reservation failure returns `budget_exhausted` without constructing the client. SDK retries remain disabled. The external timeout remains 15 seconds and is still used by official lookup. The timeout is sufficient for one extraction within the existing 60-second attempt ceiling; it does not expand the 180-second analysis budget, 20 total tool calls, or per-role cap of six. Claim fencing and persistence ownership checks are unchanged.

Collection snapshots are now version 8, so prior version 7 extraction failures cannot be reused as current results. Failure remains typed as `timeout`/`budget_exhausted`; the report keeps score null and verdict `hold`. No exception detail or credential is added to the report. The existing report and name-difference matching behavior was not modified by this patch.

No required findings.

## Independent verification

- `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/private/tmp ./.venv/bin/python -m pytest -p no:cacheprovider -s tests/test_model_timeout_review.py tests/test_agents.py tests/test_extraction_diagnosis_review.py tests/test_automatic_matching_review.py tests/test_supplement_review.py -q --tb=short`: **81 passed**. This includes a version 7 failed snapshot retry check against collection snapshot 8.
- `./.venv/bin/ruff check --no-cache src/supplement_advisor/config.py src/supplement_advisor/agents/collection_graph.py tests/test_model_timeout_review.py tests/test_extraction_diagnosis_review.py tests/test_agents.py`: passed.
- `git diff --check`: passed.
- Live model/API calls: not performed by this QA. Root owns the separately authorized final URL run and deployment manifest.
