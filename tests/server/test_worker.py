import pytest
from httpx import AsyncClient
import json
from vqec.server.models.db import TaskStatus
from tests.server.test_api_endpoints import SAMPLE_EXPERIMENT

pytestmark = pytest.mark.asyncio

async def test_heartbeat_not_found(client: AsyncClient):
    resp = await client.post("/worker/heartbeat", json={"task_ids": [99999]})
    assert resp.status_code == 404

async def test_upload_not_found(client: AsyncClient):
    from io import BytesIO
    files = {"file": ("dummy.pkl.gz", BytesIO(b"data"), "application/gzip")}
    resp = await client.post("/worker/upload/99999", data={"shots": 100, "metrics_json": "{}"}, files=files)
    assert resp.status_code == 404

async def test_download_not_found(client: AsyncClient):
    resp = await client.get("/worker/download/99999")
    assert resp.status_code == 404


async def test_download_missing_file_on_disk(client: AsyncClient, session, tmp_path, monkeypatch):
    from vqec.server.config import settings
    from vqec.server.models.db import DataGenerationTask, TaskStatus

    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))

    data_task = DataGenerationTask(
        config_hash="missing-file-hash",
        spec_json="{}",
        status=TaskStatus.COMPLETED,
        outcome_file_path=str(tmp_path / "missing.pkl.gz"),
    )
    session.add(data_task)
    await session.commit()

    resp = await client.get(f"/worker/download/{data_task.id}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "File absent on disk"


async def test_upload_exceeds_max_size(client: AsyncClient, monkeypatch):
    from io import BytesIO

    from vqec.server.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 8)

    files = {"file": ("dummy.pkl.gz", BytesIO(b"0123456789"), "application/gzip")}
    resp = await client.post(
        "/worker/upload/99999",
        data={"shots": 100, "metrics_json": "{}"},
        files=files,
    )
    assert resp.status_code == 413


async def test_complete_invalid_type_returns_422(client: AsyncClient):
    resp = await client.post(
        "/worker/complete",
        json={"type": "invalid", "id": 1, "status": "COMPLETED"},
    )
    assert resp.status_code == 422

async def test_download_success(client: AsyncClient, session, tmp_path, monkeypatch):
    from vqec.server.config import settings
    from vqec.server.models.db import DataGenerationTask, TaskStatus

    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))

    outcome = tmp_path / "outcomes" / "1.pkl.gz"
    outcome.parent.mkdir(parents=True, exist_ok=True)
    outcome.write_bytes(b"payload")

    data_task = DataGenerationTask(
        config_hash="download-success-hash",
        spec_json="{}",
        status=TaskStatus.COMPLETED,
        outcome_file_path=str(outcome),
    )
    session.add(data_task)
    await session.commit()

    resp = await client.get(f"/worker/download/{data_task.id}")
    assert resp.status_code == 200
    assert resp.content == b"payload"


async def test_complete_not_found(client: AsyncClient):
    resp = await client.post(
        "/worker/complete",
        json={"type": "data_generation", "id": 99999, "status": TaskStatus.FAILED},
    )
    assert resp.status_code == 404

    resp = await client.post(
        "/worker/complete",
        json={"type": "decoding", "id": 99999, "status": TaskStatus.COMPLETED},
    )
    assert resp.status_code == 404

async def test_worker_failure_cascade(client: AsyncClient):
    # Submit
    exp_resp = await client.post("/tasks/experiment", json=SAMPLE_EXPERIMENT)
    task_id = exp_resp.json()["id"]

    # Poll data
    poll_resp = await client.post("/worker/poll", json={"batch_size": 1, "has_gpu": False})
    tasks = poll_resp.json()["tasks"]
    data_task = tasks[0]

    # Heartbeat
    beat = await client.post("/worker/heartbeat", json={"task_ids": [data_task["id"]]})
    assert beat.status_code == 200

    # Complete data as FAILED
    comp_resp = await client.post("/worker/complete", json={
        "type": "data_generation", 
        "id": data_task["id"], 
        "status": TaskStatus.FAILED,
        "error_message": "test failure"
    })
    assert comp_resp.status_code == 200

    # Check that experiment is FAILED due to cascade, or decoding task is failed
    exp_get = await client.get(f"/tasks/experiment/{task_id}")
    assert exp_get.json()["status"] == TaskStatus.FAILED
    assert exp_get.json()["jobs"][0]["status"] == TaskStatus.FAILED

