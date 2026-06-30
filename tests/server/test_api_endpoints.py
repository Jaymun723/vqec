import pytest
from httpx import AsyncClient
import json
from vqec.server.models.db import TaskStatus

pytestmark = pytest.mark.asyncio

# Sample experiment config based on experiment_config_schema.md
SAMPLE_EXPERIMENT = {
    "name": "surface depolarizing sweep",
    "circuit": {
        "type": "stim_circuit_constructor",
        "params": {
            "name": "surface_code:rotated_memory_z",
            "distance": [3],
            "rounds": "distance"
        }
    },
    "noise": {
        "type": "depolarizing_noise",
        "params": {
            "p": "geomspace(1e-4, 1e-1, 1)"
        }
    },
    "runner": {
        "type": "stim_runner",
        "params": {
            "shots": 100,
            "seed": 42
        }
    },
    "decoder": {
        "type": "pymatching",
        "params": {
            "num_neighbours": 30
        }
    }
}

async def test_system_info(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "VQEC Server"
    assert data["status"] == "online"

async def test_get_registry(client: AsyncClient):
    response = await client.get("/registry")
    assert response.status_code == 200
    data = response.json()
    assert "circuit_constructors" in data
    assert "decoders" in data

async def test_submit_experiment(client: AsyncClient):
    response = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    if response.status_code != 200:
        print(response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == SAMPLE_EXPERIMENT["name"]
    assert data["status"] == TaskStatus.PENDING
    assert data["total_jobs"] == 1
    assert data["completed_jobs"] == 0

    task_id = data["id"]
    
    # Get details
    detail_resp = await client.get(f"/tasks/experiment/{task_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["total_jobs"] == 1
    assert len(detail["jobs"]) == 1
    assert detail["jobs"][0]["status"] == TaskStatus.PENDING

async def test_worker_poll_and_complete(client: AsyncClient):
    # Submit experiment
    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    task_id = exp_resp.json()["id"]

    # Poll for DataGenerationTask
    poll_req = {"batch_size": 1, "has_gpu": False}
    poll_resp = await client.post("/worker/poll", json=poll_req)
    assert poll_resp.status_code == 200
    tasks = poll_resp.json()["tasks"]
    assert len(tasks) == 1
    
    data_task = tasks[0]
    assert data_task["type"] == "data_generation"
    
    # Upload outcome
    upload_data = {
        "shots": 100,
        "metrics_json": json.dumps({
            "time_build_circuit_s": 0.1,
            "time_apply_noise_s": 0.1,
            "time_runner_run_s": 1.0,
            "time_pickle_write_s": 0.05
        })
    }
    
    # Mocking a file upload
    from io import BytesIO
    files = {"file": ("dummy.pkl.gz", BytesIO(b"dummy data"), "application/gzip")}
    upload_resp = await client.post(f"/worker/upload/{data_task['id']}", data=upload_data, files=files)
    assert upload_resp.status_code == 200

    # Poll again for DecodingTask
    poll_resp2 = await client.post("/worker/poll", json=poll_req)
    tasks2 = poll_resp2.json()["tasks"]
    assert len(tasks2) == 1
    
    decode_task = tasks2[0]
    assert decode_task["type"] == "decoding"
    assert decode_task["data_id"] == data_task["id"]

    # Complete DecodingTask
    complete_req = {
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
    }
    comp_resp = await client.post("/worker/complete", json=complete_req)
    assert comp_resp.status_code == 200

    # Check experiment is now COMPLETED
    detail_resp = await client.get(f"/tasks/experiment/{task_id}")
    assert detail_resp.json()["status"] == TaskStatus.COMPLETED

async def test_idempotent_submit(client: AsyncClient):
    resp1 = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    assert resp1.status_code == 200
    id1 = resp1.json()["id"]

    resp2 = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    assert resp2.status_code == 200
    id2 = resp2.json()["id"]

    assert id1 == id2
