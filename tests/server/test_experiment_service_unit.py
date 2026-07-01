import pytest
from httpx import AsyncClient

from vqec.server.models.db import TaskStatus
from tests.server.test_api_endpoints import SAMPLE_EXPERIMENT

pytestmark = pytest.mark.asyncio

async def test_cancel_completed_experiment_returns_400(client: AsyncClient, session):
    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    task_id = exp_resp.json()["id"]

    # Mark as completed manually in DB
    from vqec.server.models.db import Experiment
    exp = await session.get(Experiment, task_id)
    exp.status = TaskStatus.DONE
    session.add(exp)
    await session.commit()

    resp = await client.post(f"/tasks/experiment/{task_id}/cancel")
    assert resp.status_code == 400


async def test_retry_completed_experiment_returns_400(client: AsyncClient, session):
    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    task_id = exp_resp.json()["id"]

    from vqec.server.models.db import Experiment
    exp = await session.get(Experiment, task_id)
    exp.status = TaskStatus.DONE
    session.add(exp)
    await session.commit()

    resp = await client.post(f"/tasks/experiment/{task_id}/retry")
    assert resp.status_code == 400


async def test_submit_incompatible_experiment_returns_400(client: AsyncClient):
    # monaka_decoder requires loss_noise but sample uses depolarizing_noise
    incompatible = {
        **SAMPLE_EXPERIMENT,
        "decoder": {"type": "monaka_decoder", "params": {"include_loss_dem": True}},
    }
    resp = await client.post("/tasks/experiment", json=incompatible)
    assert resp.status_code == 400


async def test_download_not_completed_returns_400(client: AsyncClient):
    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    task_id = exp_resp.json()["id"]

    resp = await client.get(f"/tasks/experiment/{task_id}/download")
    assert resp.status_code == 400


async def test_cancel_experiment_not_found_service(session):
    from vqec.server.services.experiment import ExperimentService

    service = ExperimentService(session)
    assert await service.cancel_experiment(99999) is None


async def test_retry_experiment_not_found_service(session):
    from vqec.server.services.experiment import ExperimentService

    service = ExperimentService(session)
    assert await service.retry_experiment(99999) is None


async def test_delete_experiment_failure_returns_400(client: AsyncClient, monkeypatch):
    from vqec.server.services.experiment import ExperimentService

    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    task_id = exp_resp.json()["id"]

    async def fail_delete(self, task_id: int) -> bool:
        return False

    monkeypatch.setattr(ExperimentService, "delete_experiment", fail_delete)

    resp = await client.delete(f"/tasks/experiment/{task_id}")
    assert resp.status_code == 400


async def test_download_pending_export_returns_202(client: AsyncClient, session):
    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    task_id = exp_resp.json()["id"]

    from vqec.server.models.db import Experiment
    exp = await session.get(Experiment, task_id)
    exp.status = TaskStatus.DONE
    # Not setting result_path to trigger 202
    session.add(exp)
    await session.commit()

    resp = await client.get(f"/tasks/experiment/{task_id}/download")
    assert resp.status_code == 202
