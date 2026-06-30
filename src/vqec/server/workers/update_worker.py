import asyncio
import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from vqec.server.config import settings
from vqec.server.database import async_engine
from vqec.server.models.db import DataGenerationTask, DecodingTask, TaskStatus
from vqec.server.utils import utc_now

logger = logging.getLogger(__name__)


async def process_expired_leases() -> None:
    async with AsyncSession(async_engine) as session:
        now = utc_now()

        result_data = await session.execute(
            update(DataGenerationTask)
            .where(
                DataGenerationTask.status == TaskStatus.RUNNING,
                DataGenerationTask.leased_until < now,
            )
            .values(status=TaskStatus.PENDING, leased_until=None)
        )
        result_decode = await session.execute(
            update(DecodingTask)
            .where(
                DecodingTask.status == TaskStatus.RUNNING,
                DecodingTask.leased_until < now,
            )
            .values(status=TaskStatus.PENDING, leased_until=None)
        )
        await session.commit()

        updated_data = result_data.rowcount or 0
        updated_decode = result_decode.rowcount or 0
        if updated_data > 0 or updated_decode > 0:
            logger.info(
                "Reclaimed %s data tasks and %s decoding tasks due to lease expiration.",
                updated_data,
                updated_decode,
            )


async def run_worker() -> None:
    logger.info("Starting update worker...")
    while True:
        try:
            await process_expired_leases()
        except Exception as exc:
            logger.error("Update worker error: %s", exc)
        await asyncio.sleep(10)
