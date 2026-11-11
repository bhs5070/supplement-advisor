"""Small live-page quality sample for M1 collection-only reports.

The default sample uses two vendor product pages. Configured credentials are
ignored unless explicitly enabled; raw page contents and credentials are never
printed. This checks collection/report quality, not API persistence or full M1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from supplement_advisor.agents import run_collection_graph
from supplement_advisor.collection import collect_page
from supplement_advisor.config import get_settings

DEFAULT_PRODUCTS = (
    (
        "NOW Vitamin D3 5000 IU Softgels",
        "https://www.nowfoods.com/products/supplements/vitamin-d3-5000-iu-softgels",
    ),
    (
        "Solgar Vitamin C 1000 mg Tablets",
        "https://www.solgar.com/products/solgar-vitamin-c-1000-mg-tablets",
    ),
)


def _safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if not hostname:
            return "<invalid-url>"
        host = f"[{hostname}]" if ":" in hostname else hostname
        port = parsed.port
        netloc = f"{host}:{port}" if port is not None else host
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "<invalid-url>"


def inspect_report(report: dict[str, Any], page_text: str | None = None) -> list[str]:
    """Return contract/quality problems without judging product claims."""
    issues: list[str] = []
    required = {
        "scope", "summary", "product", "claims", "ingredients", "sources",
        "checks", "limitations", "score", "verdict", "missing_fields",
    }
    issues.extend(f"report_field_missing:{field}" for field in sorted(required - report.keys()))
    if report.get("scope") != "collection_only":
        issues.append("scope_not_collection_only")
    if report.get("score") is not None:
        issues.append("score_should_be_null")
    if report.get("verdict") != "hold":
        issues.append("verdict_should_be_hold")

    source_ids = {item.get("id") for item in report.get("sources", [])}
    if not report.get("sources"):
        issues.append("source_missing")
    checks = report.get("checks", [])
    if not checks:
        issues.append("checks_missing")
    check_names = {check.get("name") for check in checks}
    required_checks = {"페이지 수집", "표시 정보 추출", "공식 등록 대조", "개인 적합성"}
    issues.extend(
        f"check_missing:{name}" for name in sorted(required_checks - check_names)
    )
    for index, check in enumerate(checks):
        if check.get("status") not in {
            "verified", "unverified", "unavailable", "not_applicable"
        }:
            issues.append(f"check_{index}_invalid_status")
        if any(source_id not in source_ids for source_id in check.get("source_ids", [])):
            issues.append(f"check_{index}_dangling_source")

    for ingredient in report.get("ingredients", []):
        for field in ("amount", "unit", "basis"):
            if field not in ingredient:
                issues.append(f"ingredient_{field}_field_missing")
    if not isinstance(report.get("missing_fields"), list):
        issues.append("missing_fields_not_list")

    # Empty extraction with unavailable integrations is an honest unassessed
    # result, not evidence that extraction/grounding quality passed.
    if page_text is not None:
        document = "".join(page_text.casefold().split())

        def grounded(value: Any) -> bool:
            return isinstance(value, str) and "".join(value.casefold().split()) in document

        product = report.get("product") or {}
        extracted = [product.get("name"), product.get("manufacturer")]
        extracted.extend(report.get("claims", []))
        for ingredient in report.get("ingredients", []):
            extracted.append(ingredient.get("name"))
            extracted.extend(ingredient.get(field) for field in ("amount", "unit", "basis"))
        for index, value in enumerate(filter(lambda item: item is not None, extracted)):
            if not grounded(value):
                issues.append(f"extracted_value_not_in_page:{index}")
    return issues


def _settings(use_configured_keys: bool):
    settings = get_settings()
    if use_configured_keys:
        return settings
    # Do not mutate the cached Settings instance used by the application.
    return settings.model_copy(
        update={"openai_api_key": None, "food_safety_api_key": None}
    )


async def sample(products: list[tuple[str, str]], *, use_configured_keys: bool) -> dict[str, Any]:
    settings = _settings(use_configured_keys)
    results: list[dict[str, Any]] = []
    for submitted_name, url in products:
        entry: dict[str, Any] = {
            "submitted_name": submitted_name,
            "submitted_url": _safe_url(url),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            page = await collect_page(url)
            report = await run_collection_graph(page, submitted_name, settings)
            entry.update(
                {
                    "collected_page_title": page.title,
                    "report": report,
                    "quality_issues": inspect_report(report, page.text),
                    "quality_assessment": (
                        "extraction_grounding_checked"
                        if report.get("ingredients") or report.get("claims")
                        or report.get("product", {}).get("name")
                        else "not_assessed_extraction_unavailable_or_empty"
                    ),
                    "external_calls": {
                        "openai_configured": bool(settings.openai_api_key),
                        "foodsafety_configured": bool(settings.food_safety_api_key),
                        "model": settings.openai_model if settings.openai_api_key else None,
                    },
                }
            )
        except Exception as exc:
            # Do not include arbitrary exception text, which can contain URLs or secrets.
            entry.update(
                {
                    "collection_error": getattr(exc, "code", type(exc).__name__),
                }
            )
        results.append(entry)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "external_call_opt_in" if use_configured_keys else "no_external_calls",
        "external_call_opt_in": use_configured_keys,
        "sample_scope": (
            "Two US vendor product pages; not representative of Korean product coverage. "
            "FoodSafety Korea I0030 matching quality is not assessed by these samples."
        ),
        "sample_size": len(products),
        "products": results,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", action="append", default=[], metavar="URL",
        help="Public product page URL; repeat for a small sample. Defaults to two vendor pages.",
    )
    parser.add_argument(
        "--use-configured-keys", action="store_true",
        help="Allow actual OpenAI/FoodSafety API calls using configured credentials.",
    )
    parser.add_argument("--output", help="Write JSON report to this path (default: stdout).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    products = (
        [(None, url) for url in args.url]
        if args.url
        else list(DEFAULT_PRODUCTS)
    )
    result = asyncio.run(sample(products, use_configured_keys=args.use_configured_keys))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as report_file:
            report_file.write(rendered + "\n")
    else:
        sys.stdout.write(rendered + "\n")
    return 0 if all(
        not item.get("collection_error") and not item.get("quality_issues")
        for item in result["products"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
