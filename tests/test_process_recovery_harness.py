"""Opt-in real-infrastructure check for prefork process recovery and hard limits."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_PROCESS_RECOVERY") != "1",
    reason="Set RUN_PROCESS_RECOVERY=1 to run the isolated Docker failure-injection test",
)
def test_real_prefork_child_kill_and_hard_timeout_recovery():
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/verify_process_recovery.py"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REAL_PREFORK_CHILD_KILL confirmed" in result.stdout
    assert "CELERY_HARD_TIMEOUT confirmed" in result.stdout
    assert "reserved_seconds=60 reserved_tool_calls=2 stale_finish=False" in result.stdout
