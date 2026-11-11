# M1 structured product table extraction independent QA — 2026-11-10

Independent review of the stdlib `HTMLParser` fallback for explicit product information tables. QA added regression tests and did not edit product code or make live model/official API calls.

## Review focus

The tests use realistic Korean product tables plus seller/footer and related-product tables. They check that the result is identified as `structured_page`, preserves literal page identity, does not call the model or reserve an LLM call, and keeps score `null`/verdict `hold`. A mocked official lookup checks that the query uses the page's printed 품목제조신고번호, the page identity remains unchanged, and official data remains a separate source. Negative cases cover seller and 사업자등록번호 confusion, multiple 신고번호 values, malformed markup, footer completion, related-product ingredient contamination, and differing functional registration codes. Functional ingredient names and registration qualifiers are preserved verbatim. The local captured seller HTML is also parsed offline against its expected identity and ingredients.

## Findings

The first adversarial run found a false cross-table merge: a related table titled `브랜드 밸런스 플러스 상품정보` contributed its `밀크씨슬추출물` to the `브랜드 밸런스` product. The writer narrowed cross-table association to an exact product-name prefix followed by an allowlisted manufacturer-section title, and only imports manufacturer values from that section. The regression now passes. A distinct official functional registration code remains a candidate instead of being normalized into a match.

## Verification

- `tests/test_structured_extraction_review.py`, `tests/test_structured_extraction.py`, `tests/test_agents.py`, and `tests/test_extraction_diagnosis_review.py`: **80 passed**.
- Expanded related regression set including automatic matching and supplement review: **93 passed**.
- Ruff and `git diff --check`: passed.
- Offline parse of the ignored captured source `work/verification/2026-11-10-independent-seller-source.html` returned page name `이알하나 (ER Hana®)`, maker `(주)서흥`, report number `200400200062002`, and the three literal functional ingredient labels with `(제2024-17호)` preserved.

## Final URL evidence read-only review

Read `work/verification/2026-11-10-m1-structured-final-url.json` without making calls or modifying the artifact. The script status is `passed`; all 10 verification checks are true and the unauthorized read returned 404. The stored report has `extraction_status=structured_page`, `scope=collection_only`, score `null`, verdict `hold`, no supplement, no user-input source, and one official number query with total/returned 1/1. The report lists page and official records as separate sources and explicitly discloses the page/official name difference (`이알하나 (ER Hana®)` vs `이알하나 ERr731`). The direct structured path returns before model setup/budget reservation; no AI extraction success is claimed. A scan found no common credential markers in the manifest artifact. This QA did not make the live I0030 call; root owns that evidence.

The optional captured-HTML regression skips when the ignored local source artifact is absent. The fixture-based Korean HTML and all other contract checks remain portable.
