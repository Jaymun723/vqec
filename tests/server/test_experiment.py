import pytest
from httpx import AsyncClient
from vqec.server.models.db import TaskStatus
from tests.server.test_api_endpoints import SAMPLE_EXPERIMENT

pytestmark = pytest.mark.asyncio

async def test_experiment_lifecycle(client: AsyncClient):
    # 1. Submit
    resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    # 2. List
    resp = await client.get("/tasks/experiment")
    assert resp.status_code == 200
    exps = resp.json()
    assert len(exps) >= 1
    assert any(e["id"] == task_id for e in exps)
    
    resp = await client.get(f"/tasks/experiment?status={TaskStatus.PENDING}")
    assert resp.status_code == 200

    # 3. Get 404
    resp = await client.get("/tasks/experiment/99999")
    assert resp.status_code == 404

    # 4. Cancel
    resp = await client.post(f"/tasks/experiment/{task_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == TaskStatus.CANCELLED

    # Cancel not found
    resp = await client.post("/tasks/experiment/99999/cancel")
    assert resp.status_code == 404

    # 5. Retry
    resp = await client.post(f"/tasks/experiment/{task_id}/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] == TaskStatus.PENDING

    # Retry not found
    resp = await client.post("/tasks/experiment/99999/retry")
    assert resp.status_code == 404

    # 6. Delete
    resp = await client.delete(f"/tasks/experiment/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Delete not found
    resp = await client.delete("/tasks/experiment/99999")
    assert resp.status_code == 404

    # 7. Download
    resp = await client.get(f"/tasks/experiment/{task_id}/download")
    assert resp.status_code == 404 # deleted
    
async def test_experiment_invalid_submit(client: AsyncClient):
    # Missing noise params
    invalid = {**SAMPLE_EXPERIMENT, "noise": {"type": "depolarizing_noise", "params": {}}}
    resp = await client.post("/tasks/experiment", json=invalid)
    assert resp.status_code == 422
