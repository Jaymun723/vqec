import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from vqec.server.config import settings
from vqec.server.database import async_engine
from vqec.server.models.db import ExperimentTask, TaskStatus
from vqec.server.services.export import ExportService

logger = logging.getLogger(__name__)


async def process_exports() -> None:
    async with AsyncSession(async_engine) as session:
        stmt = (
            select(ExperimentTask.id)
            .where(
                ExperimentTask.status == TaskStatus.COMPLETED,
                ExperimentTask.parquet_results_path.is_(None),
            )
            .limit(10)
        )
        result = await session.execute(stmt)
        experiment_ids = result.scalars().all()

        if not experiment_ids:
            return

        export_service = ExportService(session)
        for experiment_id in experiment_ids:
            try:
                logger.info("Building parquet for experiment %s", experiment_id)
                path = await export_service.build_parquet(experiment_id)
                if path:
                    logger.info("Parquet built for experiment %s: %s", experiment_id, path)
                else:
                    logger.warning("No records found for experiment %s", experiment_id)
            except Exception as exc:
                logger.error("Failed to build parquet for experiment %s: %s", experiment_id, exc)


async def run_worker() -> None:
    logger.info("Starting export worker...")
    while True:
        try:
            if settings.export_worker:
                await process_exports()
        except Exception as exc:
            logger.error("Export worker error: %s", exc)
        await asyncio.sleep(5)
