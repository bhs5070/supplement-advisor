"""Repository behavior on isolated SQLite and optional real PostgreSQL schemas.

Set TEST_DATABASE_URL to exercise PostgreSQL, without touching existing tables.
"""

import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import event, inspect, select, update
from sqlalchemy.exc import IntegrityError

from supplement_advisor.database import make_engine, session_factory
from supplement_advisor.models import Analysis, Base
from supplement_advisor.repository import (
    accept_supplement,
    claim_analysis,
    create_analysis,
    finish_analysis,
    get_analysis,
    list_dispatchable,
    reserve_budget,
    save_snapshot,
)

PROJECT = Path(__file__).resolve().parents[1]


def migrate(engine, target="head"):
    config = Config(str(PROJECT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        if target == "base":
            command.downgrade(config, target)
        else:
            command.upgrade(config, target)


@pytest.fixture(params=["sqlite", "postgresql"])
def engine(request, tmp_path):
    if request.param == "sqlite":
        database = make_engine(f"sqlite:///{tmp_path / 'repository.db'}")
        cleanup = None
    else:
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL is not configured; real PostgreSQL unverified")
        cleanup = make_engine(url)
        if cleanup.dialect.name != "postgresql":
            cleanup.dispose()
            pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
        schema = "test_repo_" + uuid4().hex
        with cleanup.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        database = make_engine(url)

        @event.listens_for(database, "connect")
        def set_schema(dbapi_connection, connection_record):
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f'SET SESSION search_path TO "{schema}"')
            dbapi_connection.commit()

    try:
        migrate(database)
        yield database
    finally:
        database.dispose()
        if cleanup is not None:
            with cleanup.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            cleanup.dispose()


@pytest.fixture
def sessions(engine):
    return session_factory(engine)


def create(sessions):
    with sessions.begin() as session:
        row = create_analysis(
            session,
            url="https://example.com/product?private=value",
            product_name=None,
            token_hash=hashlib.sha256(b"secret guest token").hexdigest(),
        )
        return row.id


def claim(sessions, analysis_id):
    with sessions.begin() as session:
        row = claim_analysis(session, analysis_id)
        assert row is not None
        return row.claim_token, row.started_at


def expire(sessions, analysis_id):
    with sessions.begin() as session:
        session.execute(
            update(Analysis)
            .where(Analysis.id == analysis_id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )


def test_migration_matches_model_and_is_reversible(engine):
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    migrate(engine, "base")
    assert "analyses" not in inspect(engine).get_table_names()
    migrate(engine)
    assert "analyses" in inspect(engine).get_table_names()


def test_create_transaction_and_safe_repr(sessions):
    with sessions() as session:
        row = create_analysis(
            session, url="https://example.com", product_name=None, token_hash="a" * 64
        )
        analysis_id = row.id
        assert row.status == "queued"
        assert row.active_seconds_reserved == 0
        assert row.tool_calls_reserved == 0
        assert "https" not in repr(row)
        assert row.token_hash not in repr(row)
        session.rollback()
    with sessions() as session:
        assert get_analysis(session, analysis_id) is None
        with pytest.raises(ValueError, match="SHA-256"):
            create_analysis(session, url="https://example.com", product_name=None, token_hash="raw")


def test_claim_finish_and_terminal_duplicate_are_fenced(sessions):
    analysis_id = create(sessions)
    token, _ = claim(sessions, analysis_id)
    with sessions.begin() as session:
        assert claim_analysis(session, analysis_id) is None
        assert not finish_analysis(
            session, analysis_id, claim_token="wrong", status="completed", report={"bad": True}
        )
        assert finish_analysis(
            session,
            analysis_id,
            claim_token=token,
            status="completed",
            report={"scope": "collection_only", "score": None},
            raw_file="private/file.html",
        )
    with sessions.begin() as session:
        row = get_analysis(session, analysis_id)
        assert row.status == "completed"
        assert row.report["score"] is None
        assert row.raw_file == "private/file.html"
        assert row.completed_at is not None
        assert row.claim_token is None
        assert row.lease_expires_at is None
        assert claim_analysis(session, analysis_id) is None
        assert not finish_analysis(session, analysis_id, claim_token=token, status="failed")


def test_expired_worker_cannot_write_and_recovery_preserves_started_at(sessions):
    analysis_id = create(sessions)
    old_token, first_started = claim(sessions, analysis_id)
    expire(sessions, analysis_id)
    with sessions.begin() as session:
        assert not finish_analysis(session, analysis_id, claim_token=old_token, status="completed")
        assert not save_snapshot(
            session, analysis_id, claim_token=old_token, snapshot={"bad": True}
        )
        assert not reserve_budget(
            session, analysis_id, claim_token=old_token, seconds=60, tool_calls=1
        )
        assert list_dispatchable(session) == [analysis_id]
    new_token, new_started = claim(sessions, analysis_id)
    assert new_token != old_token
    assert new_started == first_started
    with sessions.begin() as session:
        assert not finish_analysis(session, analysis_id, claim_token=old_token, status="failed")
        assert finish_analysis(session, analysis_id, claim_token=new_token, status="needs_input")


def test_last_expired_attempt_is_failed_instead_of_stuck_running(sessions):
    analysis_id = create(sessions)
    for _ in range(3):
        claim(sessions, analysis_id)
        expire(sessions, analysis_id)
    with sessions.begin() as session:
        assert claim_analysis(session, analysis_id) is None
    with sessions() as session:
        row = get_analysis(session, analysis_id)
        assert row.status == "failed"
        assert row.error_code == "attempt_limit_exceeded"
        assert row.attempt_count == 3
        assert row.claim_token is None
        assert list_dispatchable(session) == []


def test_cumulative_budget_survives_crash_and_queue_wait_is_free(sessions):
    analysis_id = create(sessions)
    with sessions.begin() as session:
        session.execute(
            update(Analysis)
            .where(Analysis.id == analysis_id)
            .values(created_at=datetime.now(timezone.utc) - timedelta(days=2))
        )
    token, _ = claim(sessions, analysis_id)
    with sessions.begin() as session:
        assert reserve_budget(session, analysis_id, claim_token=token, seconds=60, tool_calls=0)
        assert reserve_budget(session, analysis_id, claim_token=token, seconds=0, tool_calls=2)
        assert save_snapshot(session, analysis_id, claim_token=token, snapshot={"node": "observed"})
    expire(sessions, analysis_id)
    token, _ = claim(sessions, analysis_id)
    with sessions.begin() as session:
        assert reserve_budget(session, analysis_id, claim_token=token, seconds=120, tool_calls=18)
        assert not reserve_budget(
            session, analysis_id, claim_token=token, seconds=0.01, tool_calls=0
        )
        assert not reserve_budget(session, analysis_id, claim_token=token, seconds=0, tool_calls=1)
    with sessions() as session:
        row = get_analysis(session, analysis_id)
        assert row.active_seconds_reserved == 180
        assert row.tool_calls_reserved == 20
        assert row.graph_snapshot == {"node": "observed"}


@pytest.mark.parametrize(
    "seconds,calls", [(float("nan"), 0), (float("inf"), 0), (-1, 0), (0, -1), (0, 0.5)]
)
def test_invalid_reservations_rejected(sessions, seconds, calls):
    analysis_id = create(sessions)
    token, _ = claim(sessions, analysis_id)
    with sessions.begin() as session, pytest.raises(ValueError):
        reserve_budget(session, analysis_id, claim_token=token, seconds=seconds, tool_calls=calls)


def test_database_rejects_impossible_lease(sessions):
    analysis_id = create(sessions)
    with pytest.raises(IntegrityError):
        with sessions.begin() as session:
            session.execute(
                update(Analysis).where(Analysis.id == analysis_id).values(status="running")
            )


def test_postgresql_supplement_acceptance_is_atomic_under_competing_updates(engine, sessions):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock race is covered by this test when configured")
    analysis_id = create(sessions)
    with sessions.begin() as session:
        session.execute(
            update(Analysis)
            .where(Analysis.id == analysis_id)
            .values(
                status="needs_input",
                report={"scope": "collection_only"},
                graph_snapshot={"old": True},
                attempt_count=2,
                active_seconds_reserved=60,
                tool_calls_reserved=3,
            )
        )
    token_hash = hashlib.sha256(b"secret guest token").hexdigest()
    barrier = Barrier(2)

    def accept(value):
        barrier.wait()
        with sessions.begin() as session:
            return accept_supplement(session, analysis_id, token_hash, {"manufacturer": value})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(accept, "Maker A"), pool.submit(accept, "Maker B")]
        assert sorted(result.result() for result in results) == [False, True]
    with sessions() as session:
        row = get_analysis(session, analysis_id)
        assert row.status == "queued"
        assert row.supplemental_input["manufacturer"] in {"Maker A", "Maker B"}
        assert row.supplemental_received_at is not None
        assert row.graph_snapshot is None
        assert row.report == {"scope": "collection_only"}
        assert (row.attempt_count, row.active_seconds_reserved, row.tool_calls_reserved) == (2, 60, 3)


def test_concurrent_delivery_has_one_claim_owner(sessions):
    analysis_id = create(sessions)
    barrier = Barrier(4)

    def try_claim(_):
        barrier.wait(timeout=10)
        with sessions.begin() as session:
            row = claim_analysis(session, analysis_id)
            return row.claim_token if row else None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(try_claim, range(4)))
    assert sum(result is not None for result in results) == 1
    with sessions() as session:
        assert get_analysis(session, analysis_id).attempt_count == 1


def test_concurrent_budget_reservations_cannot_overspend(sessions):
    analysis_id = create(sessions)
    token, _ = claim(sessions, analysis_id)
    barrier = Barrier(4)

    def try_reserve(_):
        barrier.wait(timeout=10)
        with sessions.begin() as session:
            return reserve_budget(session, analysis_id, claim_token=token, seconds=60, tool_calls=7)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(try_reserve, range(4)))
    assert sum(results) == 2
    with sessions() as session:
        row = get_analysis(session, analysis_id)
        assert row.active_seconds_reserved == 120
        assert row.tool_calls_reserved == 14


def test_postgresql_lock_wait_does_not_extend_lease(engine, sessions):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock behavior requires PostgreSQL")
    analysis_id = create(sessions)
    token, _ = claim(sessions, analysis_id)
    with sessions.begin() as session:
        session.execute(
            update(Analysis)
            .where(Analysis.id == analysis_id)
            .values(lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=1))
        )
    with sessions.begin() as locker:
        locker.scalar(select(Analysis).where(Analysis.id == analysis_id).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:

            def finish_after_lock():
                with sessions.begin() as session:
                    return finish_analysis(
                        session, analysis_id, claim_token=token, status="completed"
                    )

            future = pool.submit(finish_after_lock)
            time.sleep(1.2)
            locker.commit()
            assert not future.result(timeout=10)
