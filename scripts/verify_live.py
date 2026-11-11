"""Real API→PostgreSQL→Redis/Celery→HTTPS→LangGraph smoke check.

Requires the Compose stack. Never prints access tokens or raw response bodies.
No model or FoodSafety success is asserted when keys are absent.
"""

import argparse
import time

import httpx


def verify(base_url: str) -> None:
    with httpx.Client(base_url=base_url, timeout=20, trust_env=False) as client:
        ready = client.get("/api/ready")
        assert ready.status_code == 200 and all(ready.json().values()), "Stack is not ready"
        assert client.post("/api/analyses", json={"url": "http://127.0.0.1"}).status_code == 422
        response = client.post("/api/analyses", json={"url": "https://example.com"})
        assert response.status_code == 202, "Request was not accepted"
        accepted = response.json()
        path = f"/api/analyses/{accepted['id']}"
        assert client.get(path).status_code == 404
        assert client.get(path, headers={"X-Analysis-Token": "wrong"}).status_code == 404
        headers = {"X-Analysis-Token": accepted["access_token"]}
        deadline = time.monotonic() + 90
        result = None
        while time.monotonic() < deadline:
            response = client.get(path, headers=headers)
            assert response.status_code == 200
            result = response.json()
            if result["status"] not in {"queued", "running"}:
                break
            time.sleep(1)
        assert result and result["status"] in {"needs_input", "completed"}, "Worker did not produce a collection report"
        report = result["report"]
        assert report["scope"] == "collection_only" and report["score"] is None
        assert report["verdict"] == "hold"
        assert any(source["title"] == "Example Domain" for source in report["sources"])
        print({
            "live_stack": "passed", "analysis_id": accepted["id"],
            "status": result["status"], "scope": report["scope"],
            "capabilities": client.get("/api/capabilities").json(),
        })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    verify(parser.parse_args().base_url)
