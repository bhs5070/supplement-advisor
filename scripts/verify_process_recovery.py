"""Exercise real prefork child loss and hard timeout in an isolated Compose stack."""

import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "compose.recovery-test.yaml"
POLL_SECONDS = 2
SCENARIO_TIMEOUT = 360


class RecoveryCheckError(RuntimeError):
    pass


class Stack:
    def __init__(self, mode: str):
        self.mode = mode
        self.project = f"m1-process-recovery-{mode}"

    def run(self, *args: str, check: bool = True, timeout: int = 60) -> str:
        env = os.environ.copy()
        env["RECOVERY_FIXTURE_MODE"] = self.mode
        result = subprocess.run(
            ["docker", "compose", "-p", self.project, "-f", str(COMPOSE_FILE), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if check and result.returncode:
            raise RecoveryCheckError(
                f"Compose command failed ({args[0]}): {result.stderr[-1000:]}"
            )
        return result.stdout + result.stderr

    def psql(self, sql: str) -> str:
        result = subprocess.run(
            [
                "docker", "compose", "-p", self.project, "-f", str(COMPOSE_FILE),
                "exec", "-T", "db", "psql", "-q", "-A", "-t", "-F", "|",
                "-U", "advisor", "-d", "advisor", "-c", sql,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode:
            raise RecoveryCheckError(f"Database query failed: {result.stderr[-1000:]}")
        return result.stdout.strip()

    def row(self, analysis_id: str) -> dict:
        values = self.psql(
            "SELECT status, attempt_count, COALESCE(claim_token,''), "
            "COALESCE(lease_expires_at::text,''), "
            "COALESCE(EXTRACT(EPOCH FROM (lease_expires_at-clock_timestamp())),0), "
            "active_seconds_reserved, "
            "tool_calls_reserved, COALESCE(error_code,'') "
            f"FROM analyses WHERE id='{analysis_id}'"
        ).split("|")
        if len(values) != 8:
            raise RecoveryCheckError(f"Expected one analysis row, got {values!r}")
        return {
            "status": values[0], "attempts": int(values[1]), "token": values[2],
            "lease": values[3], "lease_remaining": float(values[4]),
            "seconds": float(values[5]), "calls": int(values[6]), "error": values[7],
        }

    def logs(self) -> str:
        return self.run("logs", "--no-color", "worker", check=False, timeout=20)

    def wait_for(self, predicate, description: str, timeout: int = SCENARIO_TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(POLL_SECONDS)
        raise RecoveryCheckError(f"Timed out waiting for {description}")

    def start(self) -> None:
        self.run("up", "-d", "--build", timeout=300)
        self.wait_for(
            lambda: "Up" in self.run("ps", check=False),
            "isolated DB, Redis, worker, and beat startup",
            timeout=90,
        )

    def insert_queued(self, analysis_id: str) -> None:
        self.psql(
            "INSERT INTO analyses (id, token_hash, url, status, attempt_count, "
            "created_at, updated_at, active_seconds_reserved, tool_calls_reserved) VALUES "
            f"('{analysis_id}', repeat('a',64), 'https://fixture.invalid/{analysis_id}', "
            "'queued', 0, clock_timestamp(), clock_timestamp(), 0, 0)"
        )

    def release(self, analysis_id: str) -> None:
        self.run("exec", "-T", "worker", "touch", f"/tmp/recovery-state/release-{analysis_id}")

    def stale_finish(self, analysis_id: str, token: str) -> str:
        # Call the product repository in-container; only its result is returned.
        source = (
            "from supplement_advisor.database import make_engine, session_factory;"
            "from supplement_advisor.repository import finish_analysis;"
            f"e=make_engine(__import__('os').environ['DATABASE_URL']);"
            f"s=session_factory(e);x=s();print(finish_analysis(x,'{analysis_id}',"
            f"claim_token='{token}',status='failed'));x.commit();x.close();e.dispose()"
        )
        result = self.run("exec", "-T", "worker", "python", "-c", source)
        return result.strip().splitlines()[-1]

    def cleanup(self) -> None:
        self.run("down", check=False, timeout=60)


def wait_log(stack: Stack, pattern: str, description: str) -> str:
    found = []

    def present():
        nonlocal found
        found = [line for line in stack.logs().splitlines() if re.search(pattern, line)]
        return bool(found)

    stack.wait_for(present, description)
    return found[-1]


def run_scenario(mode: str) -> dict:
    stack = Stack(mode)
    analysis_id = str(uuid.uuid4())
    try:
        stack.start()
        stack.insert_queued(analysis_id)
        if mode == "kill":
            entered = wait_log(stack, rf"RECOVERY_FIXTURE_ENTERED mode=kill invocation=1 .*analysis={analysis_id}", "first collection fixture")
            pid = re.search(r"pid=(\d+)", entered)
            if not pid:
                raise RecoveryCheckError("Fixture entry did not report a worker child PID")
            first = stack.row(analysis_id)
            if first["status"] != "running" or first["attempts"] != 1:
                raise RecoveryCheckError(f"Unexpected pre-kill claim: {first}")
            if first["seconds"] != 30 or first["calls"] != 1:
                raise RecoveryCheckError(f"Unexpected committed pre-kill budget: {first}")
            if not 235 <= first["lease_remaining"] <= 240 or not first["token"]:
                raise RecoveryCheckError(f"Claim did not use a fresh 240-second lease: {first}")
            # PID came from the actual prefork child executing production process_analysis.
            killer = f"import os,signal; os.kill({int(pid.group(1))}, signal.SIGKILL)"
            stack.run("exec", "-T", "worker", "python", "-c", killer)
            wait_log(stack, "WorkerLostError|Process .* exited with 'exitcode 9'", "real prefork child loss")
            after_loss = stack.row(analysis_id)
            if after_loss["status"] != "running" or after_loss["attempts"] != 1:
                raise RecoveryCheckError(f"Killed worker unexpectedly finalized the row: {after_loss}")
            print("REAL_PREFORK_CHILD_KILL confirmed; initial lease was 240 seconds")
        else:
            wait_log(stack, rf"RECOVERY_STORE_ENTERED invocation=1 analysis={analysis_id}", "synchronous store fixture")
            wait_log(stack, "RECOVERY_FIXTURE_SOFT_LIMIT_IGNORED", "soft-limit fixture continuation")
            wait_log(stack, "TimeLimitExceeded|Hard time limit .* exceeded", "Celery hard timeout")
            timed_out = stack.row(analysis_id)
            if timed_out["status"] != "running" or timed_out["attempts"] != 1:
                raise RecoveryCheckError(f"Hard timeout did not leave a reclaimable claim: {timed_out}")
            if timed_out["seconds"] != 30 or timed_out["calls"] != 1:
                raise RecoveryCheckError(f"Unexpected hard-timeout budget reservation: {timed_out}")
            print("CELERY_HARD_TIMEOUT confirmed after synchronous fixture ignored soft limit")

        wait_log(
            stack,
            rf"RECOVERY_FIXTURE_ENTERED mode={mode} invocation=2 .*analysis={analysis_id}",
            "beat recovery and second production task claim",
        )
        recovered = stack.row(analysis_id)
        if recovered["status"] != "running" or recovered["attempts"] != 2:
            raise RecoveryCheckError(f"Second claim was not fenced/running: {recovered}")
        if recovered["seconds"] != 60 or recovered["calls"] != 2:
            raise RecoveryCheckError(f"Reservations were refunded or reset across attempts: {recovered}")
        stale_result = stack.stale_finish(analysis_id, first["token"] if mode == "kill" else timed_out["token"])
        if stale_result != "False":
            raise RecoveryCheckError(f"Stale claim token was not fenced: result={stale_result!r}")
        stack.release(analysis_id)
        stack.wait_for(
            lambda: stack.row(analysis_id)["status"] in {"completed", "needs_input", "failed"},
            "terminal result from retry",
        )
        final = stack.row(analysis_id)
        if final["attempts"] != 2 or final["seconds"] != 60 or final["calls"] != 2:
            raise RecoveryCheckError(f"Final cumulative budget evidence mismatch: {final}")
        if final["status"] not in {"completed", "needs_input"}:
            raise RecoveryCheckError(f"Fixture retry did not complete: {final}")
        print(
            f"{mode}: attempts={final['attempts']} reserved_seconds={final['seconds']:.0f} "
            f"reserved_tool_calls={final['calls']} stale_finish={stale_result} "
            f"final_status={final['status']}"
        )
        return final
    finally:
        stack.cleanup()


def main() -> int:
    try:
        for mode in ("kill", "timeout"):
            run_scenario(mode)
        print("process recovery verification passed")
        return 0
    except (RecoveryCheckError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"process recovery verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
