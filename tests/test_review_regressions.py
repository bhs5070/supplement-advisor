"""Independent review regressions: public contracts and evidence boundaries."""

import asyncio
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from supplement_advisor.agents.collection_graph import Extraction, _ground_extraction
from supplement_advisor.collection import CollectionError, validate_public_url
from supplement_advisor.config import Settings
from supplement_advisor.database import make_engine
from supplement_advisor.main import create_app
from supplement_advisor.models import Base


def test_oversized_guest_token_has_same_not_found_response(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'review.db'}")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)

    async def validate(url):
        pass

    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    try:
        with TestClient(create_app(settings, engine=engine, dispatch=lambda identity: None)) as client:
            accepted = client.post("/api/analyses", json={"url": "https://example.com"}).json()
            path = f"/api/analyses/{accepted['id']}"
            expected = client.get(path, headers={"X-Analysis-Token": "wrong"})
            oversized = client.get(path, headers={"X-Analysis-Token": "x" * 257})
            assert expected.status_code == oversized.status_code == 404
            assert expected.json() == oversized.json()
    finally:
        engine.dispose()


@pytest.mark.parametrize("amount", ["1", "000"])
def test_thousands_separator_does_not_turn_amount_substring_into_value(amount):
    text = "비타민C 1,000 mg 1일 1정"
    extraction = Extraction.model_validate(
        {
            "product_name": None,
            "manufacturer": None,
            "report_number": None,
            "claims": [],
            "ingredients": [
                {"name": "비타민C", "amount": amount, "unit": "mg", "basis": None, "excerpt": text}
            ],
        }
    )
    result = _ground_extraction(extraction, text)
    assert result["ingredients"][0]["amount"] is None


async def test_broker_publication_does_not_block_the_api_event_loop(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'responsive.db'}")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    release = Event()
    dispatch_observed_release = []

    async def validate(url):
        pass

    def publish(identity):
        dispatch_observed_release.append(release.wait(timeout=0.5))

    async def concurrent_request_progress():
        await asyncio.sleep(0.02)
        release.set()

    monkeypatch.setattr("supplement_advisor.main.validate_public_url", validate)
    application = create_app(settings, engine=engine, dispatch=publish)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            response, _ = await asyncio.gather(
                client.post("/api/analyses", json={"url": "https://example.com"}),
                concurrent_request_progress(),
            )
        assert response.status_code == 202
        assert dispatch_observed_release == [True]
    finally:
        engine.dispose()


async def test_ipv6_site_local_address_is_not_public():
    with pytest.raises(CollectionError) as error:
        await validate_public_url("http://[fec0::1]/")
    assert error.value.code == "unsafe_url"
