import pytest

from vqec.server.models.db import ExperimentTask, TaskStatus
from vqec.server.services.export import ExportService

pytestmark = pytest.mark.asyncio


async def test_build_parquet_missing_experiment(session):
    service = ExportService(session)
    assert await service.build_parquet(99999) is None


async def test_build_parquet_no_decoding_jobs(session):
    experiment = ExperimentTask(
        name="empty",
        config_hash="empty-hash",
        config_json="{}",
        status=TaskStatus.COMPLETED,
    )
    session.add(experiment)
    await session.commit()

    service = ExportService(session)
    assert await service.build_parquet(experiment.id) is None
