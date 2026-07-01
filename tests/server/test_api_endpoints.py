import pytest
from httpx import AsyncClient
import json
from vqec.server.models.db import TaskStatus

pytestmark = pytest.mark.asyncio

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
    assert data["status"] == TaskStatus.IN_FLIGHT

    task_id = data["id"]
    
    detail_resp = await client.get(f"/tasks/experiment/{task_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == TaskStatus.IN_FLIGHT

async def test_idempotent_submit(client: AsyncClient):
    resp1 = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    assert resp1.status_code == 200
    id1 = resp1.json()["id"]

    resp2 = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    assert resp2.status_code == 200
    id2 = resp2.json()["id"]

    assert id1 == id2
