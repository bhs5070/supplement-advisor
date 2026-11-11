"""Bounded public HTML collection. Untrusted pages are data, never instructions.

Each hop is resolved once and connected by its validated numeric address. The
HTTPX documented ``sni_hostname`` extension preserves certificate verification
against the original hostname; Host routing is preserved separately.
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin

import httpx

MAX_URL_LENGTH = 4096
MAX_REDIRECTS = 5


class CollectionError(Exception):
    """A stable error code and safe message, with no URL or exception details."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class CollectedPage:
    url: str
    title: str
    text: str
    html: str
    image_urls: list[str]


def _parse_url(url: str) -> httpx.URL:
    if (
        not isinstance(url, str)
        or not url
        or len(url) > MAX_URL_LENGTH
        or any(ord(char) <= 32 or ord(char) == 127 for char in url)
        or "\\" in url
    ):
        raise CollectionError("invalid_url", "공개 HTTP(S) 제품 URL을 입력해 주세요.")
    try:
        parsed = httpx.URL(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.host
            or parsed.userinfo
            or parsed.port not in {None, 80 if parsed.scheme == "http" else 443}
            or "%" in parsed.host
        ):
            raise ValueError("Unsupported URL")
    except (httpx.InvalidURL, ValueError):
        raise CollectionError("invalid_url", "공개 HTTP(S) 제품 URL을 입력해 주세요.") from None
    host = parsed.host.rstrip(".").lower()
    if host in {"localhost", "local", "internal", "metadata.google.internal"} or host.endswith(
        (".localhost", ".local", ".internal")
    ):
        raise CollectionError("unsafe_url", "내부 네트워크 주소는 수집할 수 없습니다.")
    return parsed.copy_with(fragment=None)


def _public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if not ip.is_global or any(
        (ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved)
    ):
        return False
    # Reject IPv6 transition addresses instead of relying on gateway behaviour.
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.is_site_local:
            return False
        if ip.ipv4_mapped or ip.sixtofour or ip.teredo:
            return False
        if ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network(
            "64:ff9b:1::/48"
        ):
            return False
    return True


async def _resolve_public(parsed: httpx.URL) -> str:
    try:
        literal = ipaddress.ip_address(parsed.host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            answers = await asyncio.get_running_loop().getaddrinfo(
                parsed.raw_host.decode("ascii"),
                parsed.port or (443 if parsed.scheme == "https" else 80),
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except (OSError, UnicodeError):
            raise CollectionError("dns_failed", "제품 페이지 주소를 확인하지 못했습니다.") from None
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    # A mixed public/private answer is unsafe even when its first answer is public.
    if not addresses or any(not _public_ip(address) for address in addresses):
        raise CollectionError("unsafe_url", "공개 인터넷 주소만 수집할 수 있습니다.")
    return addresses[0]


async def validate_public_url(url: str) -> None:
    try:
        async with asyncio.timeout(15):
            await _resolve_public(_parse_url(url))
    except TimeoutError:
        raise CollectionError(
            "collection_timeout", "제품 페이지 주소 확인 시간이 초과되었습니다."
        ) from None


class _PageParser(HTMLParser):
    def __init__(self, url: str):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.images: list[str] = []
        self._hidden: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._hidden.append(tag)
        if self._hidden:
            return
        if tag == "title":
            self._in_title = True
        if tag == "img" and len(self.images) < 30:
            source = dict(attrs).get("src")
            if source:
                try:
                    image_url = _parse_url(urljoin(self.url, source))
                except CollectionError:
                    return
                # This list is data only; callers must revalidate before any fetch.
                candidate = str(image_url)
                if candidate not in self.images:
                    self.images.append(candidate)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._hidden:
            if tag == self._hidden[-1]:
                self._hidden.pop()
            return
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._hidden:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)
            if self._in_title:
                self.title_parts.append(text)


async def _collect(
    url: str,
    timeout: float,
    max_bytes: int,
    reserve_request: Callable[[], bool] | None = None,
) -> CollectedPage:
    current = _parse_url(url)
    # No environment proxies, cookies, redirects, auth, or implicit retries.
    async with httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    ) as client:
        for hop in range(MAX_REDIRECTS + 1):
            address = await _resolve_public(current)
            pinned = current.copy_with(host=address)
            host = current.netloc.decode("ascii")
            headers = {
                "Host": host,
                "Accept": "text/html, application/xhtml+xml",
                "Accept-Encoding": "identity",
                "User-Agent": "SupplementAdvisor/0.1 (public-page collection)",
            }
            if reserve_request is not None and not reserve_request():
                raise CollectionError("budget_exhausted", "수집 호출 한도를 초과했습니다.")
            # Client jars must not forward cookies from an unrelated numeric origin.
            client.cookies.clear()
            async with client.stream(
                "GET",
                pinned,
                headers=headers,
                extensions={"sni_hostname": current.raw_host.decode("ascii")},
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise CollectionError(
                            "invalid_redirect", "제품 페이지의 이동 주소가 없습니다."
                        )
                    if hop == MAX_REDIRECTS:
                        raise CollectionError(
                            "redirect_limit", "제품 페이지의 이동 횟수가 너무 많습니다."
                        )
                    current = _parse_url(urljoin(str(current), location))
                    continue
                if not 200 <= response.status_code < 300:
                    raise CollectionError("http_error", "제품 페이지가 정상 응답하지 않았습니다.")
                content_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                )
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise CollectionError(
                        "unsupported_content", "HTML 제품 페이지만 수집할 수 있습니다."
                    )
                if response.headers.get("content-encoding", "identity").strip().lower() not in {
                    "",
                    "identity",
                }:
                    raise CollectionError(
                        "unsupported_encoding", "압축하지 않은 제품 페이지 응답이 필요합니다."
                    )
                length = response.headers.get("content-length")
                if length and length.isdecimal() and int(length) > max_bytes:
                    raise CollectionError(
                        "page_too_large", "제품 페이지가 수집 크기 한도를 초과했습니다."
                    )
                body = bytearray()
                async for chunk in response.aiter_raw(chunk_size=65_536):
                    if len(body) + len(chunk) > max_bytes:
                        raise CollectionError(
                            "page_too_large", "제품 페이지가 수집 크기 한도를 초과했습니다."
                        )
                    body.extend(chunk)
                try:
                    html = bytes(body).decode(response.encoding or "utf-8", errors="replace")
                except LookupError:
                    html = bytes(body).decode("utf-8", errors="replace")
                parser = _PageParser(str(current))
                parser.feed(html)
                parser.close()
                return CollectedPage(
                    url=str(current),
                    title=" ".join(parser.title_parts)[:1000],
                    text="\n".join(parser.parts),
                    html=html,
                    image_urls=parser.images,
                )
    raise CollectionError("redirect_limit", "제품 페이지의 이동 횟수가 너무 많습니다.")


async def collect_page(
    url: str,
    *,
    timeout: float = 15,
    max_bytes: int = 2_000_000,
    reserve_request: Callable[[], bool] | None = None,
) -> CollectedPage:
    if timeout <= 0 or max_bytes <= 0:
        raise ValueError("timeout and max_bytes must be positive")
    try:
        async with asyncio.timeout(timeout):
            return await _collect(url, timeout, max_bytes, reserve_request)
    except TimeoutError:
        raise CollectionError(
            "collection_timeout", "제품 페이지 수집 시간이 초과되었습니다."
        ) from None
    except httpx.TimeoutException:
        raise CollectionError(
            "collection_timeout", "제품 페이지 수집 시간이 초과되었습니다."
        ) from None
    except httpx.HTTPError:
        raise CollectionError(
            "collection_failed", "제품 페이지를 안전하게 수집하지 못했습니다."
        ) from None
