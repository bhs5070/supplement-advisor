"""Test-only fixture hooks for the isolated real-Celery recovery stack."""

import asyncio
import json
import os
import time
from pathlib import Path

from billiard.exceptions import SoftTimeLimitExceeded

from supplement_advisor import tasks
from supplement_advisor.celery_app import celery_app
from supplement_advisor.collection import CollectedPage

state_path = Path("/tmp/recovery-state/invocations.json")
mode = os.environ.get("RECOVERY_FIXTURE_MODE", "kill")
production_store_html = tasks.store_html


def next_invocation(analysis_id: str) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        state = json.loads(state_path.read_text())
    except FileNotFoundError:
        state = {}
    state[analysis_id] = state.get(analysis_id, 0) + 1
    temp_path = state_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(state))
    temp_path.replace(state_path)
    return state[analysis_id]


async def fixture_collect(url: str, *, timeout: float = 15, max_bytes: int = 2_000_000):
    del timeout, max_bytes
    analysis_id = url.rsplit("/", 1)[-1]
    invocation = next_invocation(analysis_id)
    print(
        f"RECOVERY_FIXTURE_ENTERED mode={mode} invocation={invocation} "
        f"analysis={analysis_id} pid={os.getpid()}",
        flush=True,
    )
    if invocation == 2:
        gate = state_path.parent / f"release-{analysis_id}"
        while not gate.exists():
            await asyncio.sleep(0.1)
    if mode == "kill" and invocation == 1:
        await asyncio.Event().wait()
    return CollectedPage(
        url=url,
        title="Recovery fixture",
        text="Local deterministic recovery fixture.",
        html="<html><title>Recovery fixture</title><body>local fixture</body></html>",
        image_urls=[],
    )


def fixture_store_html(directory, analysis_id, claim_token, html):
    invocation = next_invocation(f"store:{analysis_id}")
    print(
        f"RECOVERY_STORE_ENTERED invocation={invocation} analysis={analysis_id} pid={os.getpid()}",
        flush=True,
    )
    if mode == "timeout" and invocation == 1:
        # Deliberately synchronous: asyncio cancellation cannot interrupt this call.
        try:
            time.sleep(120)
        except SoftTimeLimitExceeded:
            print("RECOVERY_FIXTURE_SOFT_LIMIT_IGNORED", flush=True)
            while True:
                time.sleep(1)
    return production_store_html(directory, analysis_id, claim_token, html)


tasks.collect_page = fixture_collect
tasks.store_html = fixture_store_html
celery_app.worker_main(["worker", "--loglevel=INFO", "--concurrency=1", "--pool=prefork"])
