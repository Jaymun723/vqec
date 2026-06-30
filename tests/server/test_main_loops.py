import asyncio

import pytest

from vqec.server.main import _export_loop, _lease_loop

pytestmark = pytest.mark.asyncio


async def test_export_loop_handles_process_errors(monkeypatch):
    stop = asyncio.Event()

    async def failing_exports():
        stop.set()
        raise RuntimeError("export failed")

    monkeypatch.setattr("vqec.server.workers.export_worker.process_exports", failing_exports)

    await _export_loop(stop)


async def test_export_loop_timeout_continues(monkeypatch):
    stop = asyncio.Event()
    iterations = 0

    async def noop_exports():
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            stop.set()

    async def fast_timeout(awaitable, timeout):
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
        raise TimeoutError

    monkeypatch.setattr("vqec.server.workers.export_worker.process_exports", noop_exports)
    monkeypatch.setattr(asyncio, "wait_for", fast_timeout)

    await _export_loop(stop)
    assert iterations >= 2


async def test_lease_loop_handles_process_errors(monkeypatch):
    stop = asyncio.Event()

    async def failing_leases():
        stop.set()
        raise RuntimeError("lease failed")

    monkeypatch.setattr("vqec.server.workers.update_worker.process_expired_leases", failing_leases)

    await _lease_loop(stop)


async def test_lease_loop_timeout_continues(monkeypatch):
    stop = asyncio.Event()
    iterations = 0

    async def noop_leases():
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            stop.set()

    async def fast_timeout(awaitable, timeout):
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
        raise TimeoutError

    monkeypatch.setattr("vqec.server.workers.update_worker.process_expired_leases", noop_leases)
    monkeypatch.setattr(asyncio, "wait_for", fast_timeout)

    await _lease_loop(stop)
    assert iterations >= 2
