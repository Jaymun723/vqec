import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient
from vqec.server.main import app, lifespan
from vqec.server.database import get_session
import sys

pytestmark = pytest.mark.asyncio

async def test_lifespan_and_get_session():
    # Test lifespan manually using app
    try:
        async with lifespan(app):
            # Inside lifespan
            pass
    except Exception as e:
        pytest.fail(f"Lifespan failed: {e}")

    # Test get_session directly
    gen = get_session()
    session = await anext(gen)
    assert session is not None
    try:
        await anext(gen)
    except StopAsyncIteration:
        pass

async def test_init_db():
    from vqec.server.database import init_db
    await init_db()

async def test_run_worker_handles_outer_errors(monkeypatch):
    from vqec.server.config import settings
    from vqec.server.workers.export_worker import run_worker

    async def fail_process():
        raise RuntimeError("outer failure")

    calls = 0

    async def sleep_then_cancel(seconds):
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError()

    monkeypatch.setattr(settings, "export_worker", True)
    monkeypatch.setattr("vqec.server.workers.export_worker.process_exports", fail_process)
    monkeypatch.setattr(asyncio, "sleep", sleep_then_cancel)

    with pytest.raises(asyncio.CancelledError):
        await run_worker()


async def test_update_run_worker_handles_outer_errors(monkeypatch):
    from vqec.server.workers.update_worker import run_worker

    async def fail_leases():
        raise RuntimeError("outer failure")

    async def sleep_then_cancel(seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr("vqec.server.workers.update_worker.process_expired_leases", fail_leases)
    monkeypatch.setattr(asyncio, "sleep", sleep_then_cancel)

    with pytest.raises(asyncio.CancelledError):
        await run_worker()
