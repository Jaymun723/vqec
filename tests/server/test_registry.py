import pytest
from httpx import AsyncClient
from vqec.server.models.schemas import ValidateExperimentRequest

pytestmark = pytest.mark.asyncio

async def test_get_registry_components(client: AsyncClient):
    resp = await client.get("/registry")
    assert resp.status_code == 200
    data = resp.json()
    assert "circuit_constructors" in data

    types = ["circuit-constructors", "noise-models", "runners", "decoders"]
    for t in types:
        resp = await client.get(f"/registry/{t}")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    resp = await client.get("/registry/unknown-category")
    assert resp.status_code == 404

async def test_get_registry_component(client: AsyncClient):
    resp = await client.get("/registry/decoders/monaka_decoder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "monaka_decoder"
    assert "schema" in data
    assert isinstance(data["schema"], dict)

    resp = await client.get("/registry/decoders/pymatching")
    assert resp.status_code == 200
    pymatching = resp.json()
    assert "runners" in pymatching["compatibility"]
    assert "stim_runner" in pymatching["compatibility"]["runners"]

    # Not found
    resp = await client.get("/registry/decoders/nonexistent")
    assert resp.status_code == 404

async def test_validate_experiment(client: AsyncClient):
    req = {
        "config": {
            "name": "test",
            "circuit": {"type": "stim_circuit_constructor", "params": {"name": "surface_code:rotated_memory_z", "distance": [3], "rounds": "distance"}},
            "noise": {"type": "depolarizing_noise", "params": {"p": "geomspace(1e-4, 1e-1, 1)"}},
            "runner": {"type": "stim_runner", "params": {"shots": 100, "seed": 42}},
            "decoder": {"type": "pymatching", "params": {"num_neighbours": 30}}
        }
    }

    resp = await client.post("/registry/validate-experiment", json=req)
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    assert resp.json()["jobs_count"] > 0

    incompatible_req = {
        "config": {
            **req["config"],
            "decoder": {"type": "monaka_decoder", "params": {"include_loss_dem": True}},
        }
    }
    resp = await client.post("/registry/validate-experiment", json=incompatible_req)
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
    assert resp.json()["error"] is not None

    invalid_req = {
        "config": {
            "name": "test",
            "circuit": {"type": "stim_circuit_constructor", "params": {"name": "surface_code:rotated_memory_z", "distance": [3], "rounds": "distance"}},
            "noise": {"type": "depolarizing_noise", "params": {"p": "geomspace(1e-4, 1e-1, 1)"}},
            # Missing runner
            "decoder": {"type": "pymatching", "params": {"num_neighbours": 30}}
        }
    }
    resp = await client.post("/registry/validate-experiment", json=invalid_req)
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
    assert resp.json()["error"] is not None
