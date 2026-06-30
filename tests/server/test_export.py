import pytest
from httpx import AsyncClient
import json
from vqec.server.models.db import TaskStatus
from tests.server.test_api_endpoints import SAMPLE_EXPERIMENT
from vqec.server.services.export import ExportService
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

async def test_export_worker(client: AsyncClient, session: AsyncSession):
    # Submit and complete
    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    task_id = exp_resp.json()["id"]

    poll_resp = await client.post("/worker/poll", json={"batch_size": 1, "has_gpu": False})
    data_task = poll_resp.json()["tasks"][0]

    from io import BytesIO
    files = {"file": ("dummy.pkl.gz", BytesIO(b"data"), "application/gzip")}
    await client.post(f"/worker/upload/{data_task['id']}", data={
        "shots": 100, 
        "metrics_json": json.dumps({"time_build_circuit_s": 0.1, "time_apply_noise_s": 0.1, "time_runner_run_s": 1.0, "time_pickle_write_s": 0.05})
    }, files=files)

    poll_resp2 = await client.post("/worker/poll", json={"batch_size": 1, "has_gpu": False})
    decode_task = poll_resp2.json()["tasks"][0]

    await client.post("/worker/complete", json={
        "type": "decoding",
        "id": decode_task["id"],
        "status": TaskStatus.COMPLETED,
        "metrics": {
            "logical_error_rate": 0.0,
            "n_errors": 0,
            "time_decoder_setup_s": 0.1,
            "time_decoder_decode_s": 0.1,
            "time_total_s": 0.2
        }
    })

    # Trigger export manually
    from vqec.server.workers.export_worker import process_exports
    import vqec.server.workers.export_worker
    vqec.server.workers.export_worker.async_engine = session.bind
    await process_exports()
    
    # Download
    down_resp = await client.get(f"/tasks/experiment/{task_id}/download")
    assert down_resp.status_code == 200
    assert down_resp.headers["content-type"] == "application/octet-stream"

async def test_export_missing(session: AsyncSession):
    from vqec.server.workers.export_worker import process_exports
    import vqec.server.workers.export_worker
    vqec.server.workers.export_worker.async_engine = session.bind
    await process_exports()
