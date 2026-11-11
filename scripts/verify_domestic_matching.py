"""Small, opt-in live sample of domestic product identity matching.

The default run disables configured credentials. The opt-in run uses the
existing safe HTTPX collector and collection graph, with no official-record
injection and at most one model extraction per eligible page (three total).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from supplement_advisor.agents import run_collection_graph
from supplement_advisor.collection import collect_page
from supplement_advisor.config import get_settings

PRODUCTS = (
    {
        "submitted_name": "락토핏 골드 17포",
        "url": "https://ckdhc.com/product/productView.do?category=CKD_CATE00000001&prodCode=CHC0000284",
        "expected_manufacturer_hint": "종근당건강",
    },
    {
        "submitted_name": "고려은단 비타민C 1000 120정",
        "url": "https://www.ssg.com/item/itemView.ssg?itemId=1000049983642",
        "expected_manufacturer_hint": "고려은단",
    },
    {
        "submitted_name": "정관장 에브리타임 샷",
        "url": "https://jungkwanjang.kr/products/view.do?id=1560&ref_id=1077",
        "expected_manufacturer_hint": "한국인삼공사",
    },
)

# Separate from the live product sample. These labels are control categories,
# not evidence and never receive an official record as model input.
CONTROL_CATEGORIES = (
    "wrong_manufacturer",
    "missing_report_number",
    "insufficient_identity",
)


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or "<invalid-url>"
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        return "<invalid-url>"
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _identity_observed(text: str, product: dict[str, str]) -> dict[str, bool]:
    compact = "".join(text.casefold().split())
    product_tokens = [
        "".join(token.casefold().split())
        for token in product["submitted_name"].split()
        if token
    ]
    return {
        "product_name_hint": (
            "".join(product["submitted_name"].casefold().split()) in compact
            or all(token in compact for token in product_tokens)
        ),
        "manufacturer_hint": "".join(product["expected_manufacturer_hint"].casefold().split()) in compact,
        # Report number may be labeled in Korean or appear as a 10–20 digit value.
        "report_number_marker": any(
            marker in text for marker in ("품목제조보고번호", "품목제조신고번호", "품목제조보고")
        ),
    }


def _check(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next((item for item in report.get("checks", []) if item.get("name") == name), {})


def _public_product_id(url: str) -> str | None:
    query = parse_qs(urlsplit(url).query)
    for key in ("prodCode", "itemId", "id"):
        if query.get(key):
            return query[key][0][:80]
    return None


def merge_evidence(
    prior: dict[str, Any],
    latest: dict[str, Any],
    *,
    prior_file: str,
    latest_file: str,
) -> dict[str, Any]:
    """Join separately executed evidence by public product ID, retaining provenance."""
    def normalized(item: dict[str, Any]) -> dict[str, Any]:
        product_id = item.get("source_product_id")
        if product_id not in {"CHC0000284", "1000049983642", "1560"}:
            query = parse_qs(urlsplit(item.get("source_url", "")).query)
            product_id = next(
                (query[key][0] for key in ("prodCode", "itemId", "id") if query.get(key)),
                product_id,
            )
        result = {**item, "source_product_id": product_id}
        if "identity_page_text_eligible_for_extraction" not in result:
            result["identity_page_text_eligible_for_extraction"] = result.get(
                "identity_information_sufficient_for_extraction",
                all(
                    (result.get("identity_observed_in_page") or {}).get(field)
                    for field in ("product_name_hint", "manufacturer_hint")
                ),
            )
        result.setdefault(
            "official_check_non_unavailable",
            result.get("official_match_status") in {"verified", "unverified"},
        )
        return result

    merged = {
        item["source_product_id"]: item
        for item in map(normalized, prior.get("products", []))
        if item.get("source_product_id")
    }
    merged.update(
        {
            item["source_product_id"]: item
            for item in map(normalized, latest.get("products", []))
            if item.get("source_product_id")
        }
    )
    products = [merged[key] for key in ("CHC0000284", "1000049983642", "1560") if key in merged]
    collected = [item for item in products if item.get("collection_status") == "success"]
    eligible = [
        item for item in collected if item.get("identity_page_text_eligible_for_extraction")
    ]
    complete_identity = [
        item for item in products
        if all(
            (item.get("extracted_identity") or {}).get(field)
            for field in ("name", "manufacturer", "report_number")
        )
    ]
    return {
        **latest,
        "products_attempted": len(products),
        "products": products,
        "denominators": {
            "products_attempted": len(products),
            "collection_success": len(collected),
            "identity_page_text_eligible_for_extraction": len(eligible),
            "complete_extracted_identity_name_manufacturer_number": len(complete_identity),
            "model_call_attempted": sum(
                int(item.get("denominators", {}).get("model_call_attempted", 0))
                for item in (prior, latest)
            ),
            "model_call_completed": sum(
                int(item.get("denominators", {}).get("model_call_completed", 0))
                for item in (prior, latest)
            ),
            "official_check_non_unavailable": sum(
                bool(item.get("official_check_non_unavailable")) for item in products
            ),
            "official_verified": sum(
                item.get("official_match_status") == "verified" for item in products
            ),
        },
        "merge_provenance": {
            "inputs": [prior_file, latest_file],
            "join_key": "source_product_id",
            "replacement": "latest invocation replaces the same product's earlier row",
            "separate_runs": True,
        },
    }


async def sample(
    *, use_configured_keys: bool, product_ids: set[str] | None = None
) -> dict[str, Any]:
    configured = get_settings()
    settings = configured if use_configured_keys else configured.model_copy(
        update={"openai_api_key": None, "food_safety_api_key": None}
    )
    results: list[dict[str, Any]] = []
    model_attempts = 0
    model_completed = 0

    selected_products = [
        item for item in PRODUCTS
        if product_ids is None or _public_product_id(item["url"]) in product_ids
    ]
    if product_ids is not None and len(selected_products) != len(product_ids):
        raise ValueError("Unknown product ID in restricted sample")
    for product in selected_products:
        started = datetime.now(timezone.utc).isoformat()
        entry: dict[str, Any] = {
            "submitted_name": product["submitted_name"],
            "source_url": _safe_url(product["url"]),
            "source_product_id": _public_product_id(product["url"]),
            "retrieved_at": started,
            "expected_source_identity": product["expected_manufacturer_hint"],
        }
        try:
            page = await collect_page(product["url"])
        except Exception as exc:
            entry.update({"collection_status": "failed", "collection_error": getattr(exc, "code", type(exc).__name__)})
            results.append(entry)
            continue

        identity = _identity_observed(page.text, product)
        entry.update(
            {
                "collection_status": "success",
                "page_title": page.title,
                "identity_observed_in_page": identity,
                "page_excerpt": page.text[:1600],
                "identity_page_text_eligible_for_extraction": (
                    identity["product_name_hint"] and identity["manufacturer_hint"]
                ),
            }
        )
        # A title-only/dynamic page is retained in the denominator and is not
        # sent to the paid model without enough visible identity text.
        if not entry["identity_page_text_eligible_for_extraction"]:
            entry.update({"extraction_status": "not_attempted_insufficient_page_text", "report": None})
            results.append(entry)
            continue

        if settings.openai_api_key:
            model_attempts += 1
        report = await run_collection_graph(page, product["submitted_name"], settings)
        extraction = _check(report, "표시 정보 추출")
        official = _check(report, "공식 등록 대조")
        if settings.openai_api_key and extraction.get("status") == "unverified":
            model_completed += 1
        entry.update(
            {
                "extraction_status": extraction.get("status"),
                "model_call_attempted": bool(settings.openai_api_key),
                "model_call_completed": bool(
                    settings.openai_api_key and extraction.get("status") == "unverified"
                ),
                "official_check_non_unavailable": official.get("status") in {
                    "verified", "unverified"
                },
                "extracted_identity": report.get("product", {}),
                "official_match_status": official.get("status"),
                "official_match_detail": official.get("detail"),
                "official_response_observation": (
                    {
                        "product_name": report.get("product", {}).get("name"),
                        "manufacturer": report.get("product", {}).get("manufacturer"),
                        "report_number": report.get("product", {}).get("report_number"),
                        "official_record_excerpt": (
                            next(
                                (source.get("excerpt") for source in report.get("sources", [])
                                 if source.get("kind") == "official"),
                                None,
                            )
                        ),
                        "record_values_exposed_by_graph": any(
                            source.get("kind") == "official"
                            for source in report.get("sources", [])
                        ),
                        "comparison_status": official.get("status"),
                    }
                    if official.get("status") in {"verified", "unverified"}
                    else "not_observed"
                ),
                "official_source": next(
                    (source for source in report.get("sources", []) if source.get("kind") == "official"),
                    None,
                ),
                "report": report,
            }
        )
        results.append(entry)

    collected = [item for item in results if item.get("collection_status") == "success"]
    identity_observed = [
        item for item in collected if item.get("identity_page_text_eligible_for_extraction")
    ]
    complete_extracted_identity = [
        item for item in results
        if all(
            (item.get("extracted_identity") or {}).get(field)
            for field in ("name", "manufacturer", "report_number")
        )
    ]
    official_attempted = [
        item for item in results if item.get("official_match_status") not in {None, "unavailable"}
    ]
    verified = [item for item in results if item.get("official_match_status") == "verified"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "external_call_opt_in" if use_configured_keys else "no_external_calls",
        "external_call_opt_in": use_configured_keys,
        "sample_frame_size": len(PRODUCTS),
        "products_attempted_this_run": len(selected_products),
        "denominators": {
            "products_attempted_this_run": len(selected_products),
            "collection_success": len(collected),
            "identity_page_text_eligible_for_extraction": len(identity_observed),
            "complete_extracted_identity_name_manufacturer_number": len(complete_extracted_identity),
            "model_call_attempted": model_attempts,
            "model_call_completed": model_completed,
            "official_check_non_unavailable": len(official_attempted),
            "official_verified": len(verified),
        },
        "control_categories_not_mixed_into_live_sample": list(CONTROL_CATEGORIES),
        "limitations": [
            "작은 편의 표본이며 국내 제품 전반의 정확도·수집률 추정치가 아닙니다.",
            "공식 API 결과는 모델 입력에 주입하지 않았습니다. 미일치 I0030 row의 필드 값은 graph 보고서에 노출되지 않아 필드별 비교가 불가합니다.",
            "페이지 이미지의 신고번호는 OCR하지 않았습니다. JS 전용·이미지 전용 정보는 미확인입니다.",
            "verified가 0이면 이 표본에서 positive를 관찰하지 못한 것이며 미등록 판단이 아닙니다.",
        ],
        "products": results,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--use-configured-keys",
        action="store_true",
        help="Explicitly allow up to three model calls and I0030 lookups.",
    )
    parser.add_argument("--output", type=Path, help="Write evidence JSON to this path.")
    parser.add_argument(
        "--only-product-id",
        help="Restrict this invocation to one public product identifier; sample frame remains three.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = asyncio.run(
        sample(
            use_configured_keys=args.use_configured_keys,
            product_ids={args.only_product_id} if args.only_product_id else None,
        )
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
