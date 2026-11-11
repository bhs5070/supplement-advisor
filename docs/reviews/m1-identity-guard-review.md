# M1 identity guard independent review

Date: 2026-11-11  
Reviewed collection graph SHA256: `b3f33cf6596b37ab14f48961ada5427ee4168542bb651a9038ff8dcf50b9f429`  
Reviewed structured table parser SHA256: `cafff9530a18e0fac918d7e7c3703099ea682f5ed13a1793c249b0b0b1418ce5`  
Offline replay artifact SHA256: `67c7712cd03518c18e6e7f0631c4b1fb0529a96e613e876804e2d0c3c313180f`

## Result

The requested independent guard checks passed. No product source was edited, no model or official API call was made, and the original baseline, labels, and cached HTML were not changed.

The independent suite covers the specific high-risk boundaries:

- Model extraction of the exact placeholder `상세페이지 참조` is withheld.
- A footer legal entity or seller-only company is not accepted as manufacturer.
- In one source row containing `제조원: 회사A / 판매원: 회사B`, company A is accepted and company B is rejected. An explicitly joint `제조원 및 판매원: 회사B` role remains accepted.
- The prefix `콜마비앤에이치(주)` is rejected for a source value `콜마비앤에이치(주)음성공장`; the exact full factory value is accepted.
- The real cached GS Daypack row keeps `콜마비앤에이치(주)음성공장` as manufacturer.
- ER Hana's direct table path still returns the product identity, manufacturer, report number, and three functional ingredients with `structured_page`; the model client is forbidden in the test and is not invoked.

`tests/test_identity_guard_review.py` also checks the saved offline replay artifact's stage 1 artifact hash, stage 1 manifest hash, current collection graph hash, all six cache HTML hashes, and zero model/API/baseline rerun counts. The artifact reports five manufacturer values kept and two identity values withheld. One kept value (`kgc-387`) is based on a synthetic grounded label because the original baseline model did not extract a manufacturer; the artifact explicitly says this is not a replay of the original model extraction. The other source values are offline guard-helper replays, not additional model outputs.

## Verification

- `.venv/bin/python -m pytest tests/test_identity_guard_review.py -q --tb=short`: 9 passed.
- `.venv/bin/ruff check tests/test_identity_guard_review.py`: passed.
- `git diff --check -- tests/test_identity_guard_review.py`: passed.
- Raw artifact review: diagnostic provider calls are all zero; cache HTML SHA256 values match the replay artifact.

The root separately reported deployment source hash equality and a successful 10/10 new ER Hana structured extraction path with model calls at zero. That live deployment evidence is not part of this independent offline test run.

## Disposition

No required finding remains within the assigned guard scope. These checks cover the specified placeholder, manufacturer role binding, factory-name exactness, real Daypack manufacturer source, and ER Hana direct-table non-regression cases. They do not certify general extraction quality or live provider behavior. This records only completion of the bounded M1 guard review; M2 remains on hold at the user's direction and this review does not authorize M2 work.
