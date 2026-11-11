# M1 stage 1 result adjudication

Date: 2026-11-11  
Stage 1 artifact: `work/verification/2026-11-11-m1-evaluation-stage1.json`  
Artifact SHA256: `eb34713245153ba40e2c227f156b734b38db37cd8fd32f51e2e0ce92ea4a1ed8`  
Run ID: `90e66f60d55248d4`  
Annotated v2 manifest SHA256: `d66c8c55d766c5850c14c505837d322be8565ad64e0965f2659b32a729a1853c`  
Harness SHA256 recorded by run: `4d4da3dece7b49f990e54c556153d235394b5e3332146868c7016a00767a0b6c`

## Scope and method

This is a read-only review of the saved stage 1 JSON, frozen v2 annotations, and the raw HTML cache files referenced by sample ID. Each matched sample's cached HTML SHA256 agrees with its artifact `source_sha256`. No URL, model, or official API was called for this review. The official record below is the response saved by stage 1; I compared its recorded identity fields and evidence to the cached seller page. Gold labels remain unchanged. Additional manual judgements are described separately and do not replace unknown labels.

The artifact uses the same v2 manifest hash, has all 20 fixed sample IDs, and reports 16 cached HTML inputs plus 4 collection failures. It records 15 model requests, one structured-page extraction, and 26 official provider requests. Failed samples were not replaced. The prediction states were 2 matched, 7 candidate, 6 unverified, and 5 unknown.

## Matched outputs

| Sample | Frozen official label | Saved prediction | Read-only source adjudication |
|---|---|---|---|
| `er-15` | Known registration `200400200062002` | `matched`; identity outcome `true_match` | **Supported; no false match found.** The page itself shows the same registration number and manufacturer `(주)서흥`. It shows the ER Hana / ERr731 product title and the same three principal ingredients as the saved I0030 record. The only name conflict is the expected seller name versus official registered name; both names and the ERr731 ingredient are present on the page. The saved number lookup returned one complete record. The official shape is `정`; the page also says one tablet, although the extraction evidence did not provide a dosage-form comparison. Keep the recorded `true_match`; do not imply evidence beyond the saved record and page.
| `gs-daypack` | Unknown registration; report number not in page | `matched`; identity outcome `unjudged` | **Strong corroboration, but still unjudged against gold.** The seller page identifies “데이팩 올인원”, names `콜마비앤에이치(주)음성공장`, and lists the additional ingredients used in the match evidence. Its intake text specifies one pack with one tablet, one hard capsule, and two soft capsules; the saved official record has the same intake instruction. A complete four-record name search includes one exact name/manufacturer record and three distinguishable variants. The page does not show the selected report number, and the frozen official-registration label is unknown. Do not count this as a gold `true_match` or change that label. The saved evidence contains no page/API contradiction that demonstrates a false match.

The two `matched` predictions therefore comprise one independently known positive supported by the page and one source-corroborated but gold-unjudged case. They do not establish a matched-result precision rate: only one sample has a known registration label, and there is no known negative registration label in the 20-item corpus. The observed false-match count of zero is not a general safety result.

## Additional extraction findings

### `gs-womanpack`: placeholder treated as a product name

The listing title and product schema identify the product as the LipoDay All-in-One Woman Pack. The product-information table uses “상세페이지 참조” for several fields, including `제품명`. The extraction returned that placeholder as `product.name`, and official lookup queried both the spaced and unspaced placeholder. Both searches returned zero rows; the final state remained `unverified`, not matched. The sample's frozen name label is known, so this is a genuine extraction miss among the measured name outcomes, but not a false official match.

**Severity:** high-priority extraction/input-quality defect; no incorrect confirmation occurred in this sample.  
**Smallest conservative fix:** recognize exact “상세페이지 참조” as a placeholder and suppress it as an identity value. Do not call official search with it; report the name as unavailable unless another directly observed product-title field supplies a grounded identity.

### `er-56`: footer legal entity assigned as manufacturer

The page shows the product title and a footer `법인명(상호)` value `주식회사 시나몬랩`. The cached page does not show that company in a product-specific manufacturer field. The extraction assigned the footer legal entity to `product.manufacturer`; the official search by product name returned no candidates and the result remained `unverified`. Manufacturer truth is unknown for this sample, so this is not a labeled incorrect outcome and did not cause a false match here.

**Severity:** high-priority grounding defect because a seller/legal entity can be mistaken for a manufacturer and affect candidate selection.  
**Smallest conservative fix:** accept a manufacturer only when an explicit manufacturing-role label (for example, `제조원` or `제조업소`) and its value occur together in the same product-information row/block. Never borrow `법인명`, seller, distributor, or site-owner values.

### `gs-gnm-allinone`: exact-string label mismatch

The extracted name is the seller's full displayed offer title, including promotion, quantity, and several product terms; the expected canonical product name occurs inside that title. The saved page supports the title as displayed, while the frozen annotation lists shorter product-name forms. The exact normalized comparison counts this as `incorrect`. No official match was produced (`request_failed`).

**Disposition:** likely an annotation granularity / exact-match metric mismatch rather than evidence of a different product. Keep the frozen label and the original `incorrect` metric unchanged. If a separate post-hoc identity judgement is recorded, retain the raw displayed title and the reason it maps to the canonical product name; do not rewrite the v2 annotation or turn this into a stage 1 success.

## Denominators and limits

The stage 1 metrics report product-name outcomes as 13 correct, 2 incorrect, 1 missing, and 4 unjudged among 16 known / 4 unknown labels. Manufacturer outcomes are 4 correct and 1 missing among 5 known, with 15 unknown. Report-number outcomes are 1 correct, 15 `expected_missing`, and 4 unjudged; the 15 `not_in_page` labels mean the number was absent from the observed page, not that the product is unregistered. Official-registration labels are 1 known / 19 unknown; outcomes are 1 `true_match` / 19 `unjudged`. Preserve all of these original denominators.

This is a fixed convenience sample with 4 HTTP collection failures and 16 reused cached HTML documents. It does not establish representative site coverage, an overall extraction success rate, or official-match safety. The raw stage 1 run is the measured baseline; the findings above are post-hoc adjudications, not replacements for its predictions or labels.

## Disposition

No false official match was demonstrated among the two saved matched outputs. `er-15` is supported for its known label. `gs-daypack` remains gold-unjudged despite strong source corroboration. The placeholder-name and footer-manufacturer errors are important conservative-input defects; they should be handled by narrow extraction guards, without changing baseline artifacts or adding model/API calls. The GNM title case remains a label-granularity discrepancy for separate post-hoc review.
