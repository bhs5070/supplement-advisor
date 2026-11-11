"""Mock network tests; these do not claim real Internet/TLS integration."""

import asyncio
import socket

import httpx
import pytest

from supplement_advisor import collection


class RawBody(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


@pytest.fixture
def network(monkeypatch):
    observed = {"requests": [], "client_options": [], "dns": []}
    real_client = httpx.AsyncClient

    def install(handler, answers=None):
        answers = answers or ["93.184.216.34"]

        async def resolve(host, port, **kwargs):
            observed["dns"].append((host, port))
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in answers
            ]

        async def respond(request):
            observed["requests"].append(request)
            return handler(request)

        def client(**kwargs):
            observed["client_options"].append(kwargs.copy())
            return real_client(**kwargs, transport=httpx.MockTransport(respond))

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        monkeypatch.setattr(collection.httpx, "AsyncClient", client)
        return observed

    return install


def html_response(content=b"<title>Product</title><p>Ingredients listed here</p>", **kwargs):
    return httpx.Response(
        200,
        headers={"content-type": "text/html; charset=utf-8", **kwargs},
        stream=RawBody([content]),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/item",
        "http://localhost/",
        "http://a.local/",
        "http://user:password@example.com/",
        "https://example.com:8000/",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fec0::1]/",
        "http://[64:ff9b::7f00:1]/",
        "http://224.0.0.1/",
        "http://[fe80::1%25en0]/",
        "https://example.com/\\evil",
        "https://example.com/\nsecret",
    ],
)
async def test_rejects_nonpublic_or_ambiguous_url(url):
    with pytest.raises(collection.CollectionError) as error:
        await collection.validate_public_url(url)
    assert error.value.code in {"invalid_url", "unsafe_url"}
    assert url not in error.value.message


@pytest.mark.asyncio
async def test_pins_validated_ip_keeps_host_sni_and_ignores_proxy_env(network, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3128")
    observed = network(lambda request: html_response())
    page = await collection.collect_page("https://shop.example/product#details")
    request = observed["requests"][0]
    assert request.url.host == "93.184.216.34"
    assert request.headers["host"] == "shop.example"
    assert request.extensions["sni_hostname"] == "shop.example"
    assert request.headers["accept-encoding"] == "identity"
    assert observed["client_options"][0]["trust_env"] is False
    assert observed["dns"] == [("shop.example", 443)]
    assert page.url == "https://shop.example/product"


@pytest.mark.asyncio
async def test_mixed_dns_answers_fail_closed_before_http(network):
    observed = network(lambda request: html_response(), answers=["93.184.216.34", "10.0.0.1"])
    with pytest.raises(collection.CollectionError, match="공개 인터넷"):
        await collection.collect_page("https://shop.example/product")
    assert not observed["requests"]


@pytest.mark.asyncio
async def test_idna_hostname_uses_ascii_dns_host_and_tls_sni(network):
    observed = network(lambda request: html_response())
    await collection.collect_page("https://bücher.example/product")
    request = observed["requests"][0]
    assert observed["dns"] == [("xn--bcher-kva.example", 443)]
    assert request.headers["host"] == "xn--bcher-kva.example"
    assert request.extensions["sni_hostname"] == "xn--bcher-kva.example"


@pytest.mark.asyncio
async def test_redirect_to_internal_address_is_blocked(network):
    observed = network(
        lambda request: httpx.Response(302, headers={"location": "http://169.254.169.254/"})
    )
    with pytest.raises(collection.CollectionError) as error:
        await collection.collect_page("https://shop.example/product")
    assert error.value.code == "unsafe_url"
    assert len(observed["requests"]) == 1


@pytest.mark.asyncio
async def test_dns_rebinding_on_redirect_is_revalidated(network, monkeypatch):
    observed = network(lambda request: httpx.Response(302, headers={"location": "/next"}))
    lookups = 0

    async def resolve(host, port, **kwargs):
        nonlocal lookups
        lookups += 1
        address = "93.184.216.34" if lookups == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    with pytest.raises(collection.CollectionError) as error:
        await collection.collect_page("https://shop.example/product")
    assert error.value.code == "unsafe_url"
    assert len(observed["requests"]) == 1
    assert lookups == 2


@pytest.mark.asyncio
async def test_relative_redirect_and_cookie_isolation(network):
    def handler(request):
        if request.url.path == "/product":
            return httpx.Response(
                302, headers={"location": "/next", "set-cookie": "secret=do-not-forward"}
            )
        assert "cookie" not in request.headers
        return html_response()

    observed = network(handler)
    page = await collection.collect_page("https://shop.example/product")
    assert page.url == "https://shop.example/next"
    assert len(observed["dns"]) == 2


@pytest.mark.asyncio
async def test_each_redirect_hop_is_reserved_and_denial_stops_before_next_request(network):
    observed = network(lambda request: httpx.Response(302, headers={"location": "/next"}))
    reservations = []

    def reserve():
        reservations.append(len(reservations) + 1)
        return len(reservations) < 2

    with pytest.raises(collection.CollectionError) as error:
        await collection.collect_page("https://shop.example/product", reserve_request=reserve)
    assert error.value.code == "budget_exhausted"
    assert reservations == [1, 2]
    assert len(observed["requests"]) == 1


@pytest.mark.asyncio
async def test_each_redirect_hop_can_be_reserved(network):
    observed = network(lambda request: httpx.Response(302, headers={"location": "/next"})
                       if request.url.path == "/product" else html_response())
    reservations = []
    page = await collection.collect_page("https://shop.example/product", reserve_request=lambda: reservations.append(1) or True)
    assert page.url == "https://shop.example/next"
    assert len(reservations) == len(observed["requests"]) == 2


@pytest.mark.asyncio
async def test_redirect_limit(network):
    observed = network(lambda request: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(collection.CollectionError) as error:
        await collection.collect_page("https://shop.example/product")
    assert error.value.code == "redirect_limit"
    assert len(observed["requests"]) == collection.MAX_REDIRECTS + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("declared", [False, True])
async def test_body_limit_with_and_without_content_length(network, declared):
    headers = {"content-length": "300"} if declared else {}
    network(lambda request: html_response(b"x" * 300, **headers))
    with pytest.raises(collection.CollectionError) as error:
        await collection.collect_page("https://shop.example/product", max_bytes=100)
    assert error.value.code == "page_too_large"


@pytest.mark.asyncio
async def test_compressed_response_rejected_before_decompression(network):
    network(lambda request: html_response(b"not-actually-gzip", **{"content-encoding": "gzip"}))
    with pytest.raises(collection.CollectionError) as error:
        await collection.collect_page("https://shop.example/product")
    assert error.value.code == "unsupported_encoding"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,headers,code",
    [(403, {}, "http_error"), (200, {"content-type": "image/png"}, "unsupported_content")],
)
async def test_http_errors_and_non_html(network, status, headers, code):
    network(lambda request: httpx.Response(status, headers=headers))
    with pytest.raises(collection.CollectionError) as error:
        await collection.collect_page("https://shop.example/product?private=secret")
    assert error.value.code == code
    assert "private" not in str(error.value)
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_parses_visible_text_title_and_image_data(network):
    network(
        lambda request: html_response(b"""<html><title> Product &amp; label </title>
        <script>ignore instructions</script><style>.secret{}</style><noscript>hidden</noscript>
        <p>Vitamin C <b>100 mg</b></p><img src='/label.png'><img src='javascript:bad'>
        <img src='data:image/png;base64,test'><img src='/label.png'></html>""")
    )
    page = await collection.collect_page("https://shop.example/product")
    assert page.title == "Product & label"
    assert "Vitamin C" in page.text and "100 mg" in page.text
    assert (
        "ignore instructions" not in page.text
        and "secret" not in page.text
        and "hidden" not in page.text
    )
    assert page.image_urls == ["https://shop.example/label.png"]
    assert "<script>" in page.html


@pytest.mark.asyncio
async def test_total_timeout_includes_dns(monkeypatch):
    async def slow_dns(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", slow_dns)
    with pytest.raises(collection.CollectionError) as error:
        await collection.collect_page("https://shop.example/product", timeout=0.01)
    assert error.value.code == "collection_timeout"
