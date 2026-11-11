"""Conservative extraction of explicit Korean product-information table labels."""

from __future__ import annotations

import re
from html.parser import HTMLParser


class _ProductTableParser(HTMLParser):
    _IGNORED_TAGS = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[tuple[str, list[list[tuple[str, str]]]]] = []
        self._table: list[list[tuple[str, str]]] | None = None
        self._row: list[tuple[str, str]] | None = None
        self._cell_tag: str | None = None
        self._parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._IGNORED_TAGS:
            self._ignored += 1
        if self._ignored:
            return
        if tag == "table":
            self._table = []
        elif tag == "tr":
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell_tag, self._parts = tag, []

    def handle_endtag(self, tag):
        if tag in self._IGNORED_TAGS and self._ignored:
            self._ignored -= 1
        if self._ignored:
            return
        if tag in {"th", "td"} and self._cell_tag:
            value = re.sub(r"\s+", " ", " ".join(self._parts)).strip()
            self._row.append((self._cell_tag, value))
            self._cell_tag, self._parts = None, []
        elif tag == "tr" and self._row:
            if self._table is not None:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            title = self._table[0][0][1] if self._table and len(self._table[0]) == 1 else ""
            self.tables.append((title, self._table))
            self._table = None

    def handle_data(self, data):
        if not self._ignored and self._cell_tag:
            self._parts.append(data)


def _label(value: str) -> str:
    value = re.sub(r"^[\s①②③④⑤⑥⑦⑧⑨⑩\d.)-]+", "", value)
    return re.sub(r"[\s:：·ㆍ]", "", value).casefold()


def _manufacturer_section_for_product(title: str, product_name: str) -> bool:
    title_key = _label(title)
    product_key = _label(product_name)
    if not title_key.startswith(product_key):
        return False
    section = title_key[len(product_key) :]
    return section in {
        "제조및표시사항",
        "제조및표시정보",
        "제조업소정보",
        "제조원정보",
    }


def _labelled_tables(html: str):
    parser = _ProductTableParser()
    parser.feed(html)
    for title, table in parser.tables:
        values = []
        for row in table:
            cells = [value for _, value in row]
            for label, value in zip(cells[::2], cells[1::2]):
                if label and value:
                    values.append((_label(label), value))
        yield title, values


def extract_product_table(html: str) -> dict | None:
    """Return structured facts only when one explicit table supplies all required fields."""
    parser_tables = list(_labelled_tables(html))
    successful = []
    for title, values in parser_tables:
        found: dict[str, set[str]] = {key: set() for key in ("name", "manufacturer", "number")}
        ingredient_names: set[str] = set()
        def consume(label, value):
            if label in {"제품명", "상품명"}:
                found["name"].add(value)
            elif ("제조업소" in label or "전문제조원" in label or label == "제조원") and "판매" not in label:
                manufacturer = re.split(r"\s*/\s*", value, maxsplit=1)[0].strip()
                manufacturer = re.sub(
                    r"^\[(?:건강기능식품)?(?:전문)?제조(?:업소|원)\]\s*", "", manufacturer
                ).strip()
                if manufacturer:
                    found["manufacturer"].add(manufacturer)
            elif label in {"품목제조신고번호", "품목제조보고번호"}:
                digits = re.sub(r"\s", "", value)
                if re.fullmatch(r"\d{5,20}", digits):
                    found["number"].add(digits)
            elif label in {"기능정보", "기능성정보"}:
                for item in re.findall(r"\[([^\[\]]+)\]", value):
                    name = item.strip()
                    if re.search(r"[가-힣A-Za-z]", name):
                        ingredient_names.add(name)

        for label, value in values:
            consume(label, value)
            # Some retailer tables put a second explicit label in the value cell.
            for match in re.finditer(r"(?:품목제조신고번호|품목제조보고번호)\s*[:：]?\s*(\d{5,20})", value):
                consume("품목제조신고번호", match.group(1))
        product_name = next(iter(found["name"])) if len(found["name"]) == 1 else ""
        if product_name and title:
            for other_title, other_values in parser_tables:
                if other_title and _manufacturer_section_for_product(other_title, product_name):
                    for label, value in other_values:
                        if (
                            "제조업소" in label or "전문제조원" in label or label == "제조원"
                        ) and "판매" not in label:
                            consume(label, value)
        if all(len(found[key]) == 1 for key in found) and ingredient_names:
            successful.append((found, ingredient_names))
    if len(successful) != 1:
        return None
    found, ingredient_names = successful[0]
    name = next(iter(found["name"]))
    manufacturer = next(iter(found["manufacturer"]))
    number = next(iter(found["number"]))
    return {
        "product_name": {"value": name, "excerpt": name},
        "manufacturer": {"value": manufacturer, "excerpt": manufacturer},
        "report_number": {"value": number, "excerpt": number},
        "claims": [],
        "ingredients": [
            {"name": value, "amount": None, "unit": None, "basis": None, "excerpt": value}
            for value in sorted(ingredient_names)
        ],
    }
