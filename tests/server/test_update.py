import pytest
from httpx import AsyncClient
from vqec.server.models.db import TaskStatus
from tests.server.test_api_endpoints import SAMPLE_EXPERIMENT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from vqec.server.models.db import DataGenerationTask
from datetime import datetime, timezone, timedelta

pytestmark = pytest.mark.asyncio

async def test_update_expired_leases(client: AsyncClient, session: AsyncSession):
    # Submit
    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    
    # Poll
    poll_resp = await client.post("/worker/poll", json={"batch_size": 1, "has_gpu": False})
    tasks = poll_resp.json()["tasks"]
    data_task = tasks[0]

    # Force expiration in DB
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    stmt = update(DataGenerationTask).where(DataGenerationTask.id == data_task["id"]).values(leased_until=past)
    await session.execute(stmt)
    await session.commit()

    # Process manually
    from vqec.server.workers.update_worker import process_expired_leases
    import vqec.server.workers.update_worker
    vqec.server.workers.update_worker.async_engine = session.bind
    await process_expired_leases()

    # Verify task is back to PENDING
    from sqlmodel import select
    res = await session.execute(select(DataGenerationTask).where(DataGenerationTask.id == data_task["id"]))
    dt = res.scalars().first()
    assert dt.status == TaskStatus.PENDING
    assert dt.leased_until is None

