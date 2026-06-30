import pytest
from unittest.mock import AsyncMock, patch

from vqec.server.models.db import ExperimentTask, TaskStatus
from vqec.server.services.export import ExportService
from vqec.server.workers.export_worker import process_exports
from vqec.server.workers.update_worker import process_expired_leases

pytestmark = pytest.mark.asyncio


async def test_process_exports_logs_build_failure(session):
    import vqec.server.workers.export_worker as export_worker_module

    experiment = ExperimentTask(
        name="export-fail",
        config_hash="export-fail-hash",
        config_json="{}",
        status=TaskStatus.COMPLETED,
    )
    session.add(experiment)
    await session.commit()

    export_worker_module.async_engine = session.bind

    with patch.object(
        ExportService,
        "build_parquet",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await process_exports()


async def test_process_exports_warns_when_no_records(session):
    import vqec.server.workers.export_worker as export_worker_module

    experiment = ExperimentTask(
        name="no-records",
        config_hash="no-records-hash",
        config_json="{}",
        status=TaskStatus.COMPLETED,
    )
    session.add(experiment)
    await session.commit()

    export_worker_module.async_engine = session.bind
    await process_exports()


async def test_process_expired_leases(session):
    import vqec.server.workers.update_worker as update_worker_module

    update_worker_module.async_engine = session.bind
    await process_expired_leases()
