"""End-to-end test: real server process + real compute worker process."""

import io
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import httpx
import pandas as pd
import pytest

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stop_process(proc: subprocess.Popen | None, *, grace_seconds: float = 5) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait()


def test_full_distributed_e2e():
    """
    1. Spawn the FastAPI server in a background process.
    2. Submit an experiment via HTTP.
    3. Spawn the compute worker in a background process.
    4. Wait for the experiment to reach COMPLETED.
    5. Download Parquet results and verify contents.
    """
    port = _free_port()
    api_url = f"http://127.0.0.1:{port}"

    server_proc = None
    worker_proc = None

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "e2e_test.db")
        env = os.environ.copy()
        env["VQEC_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        env["VQEC_STORAGE_DIR"] = temp_dir
        # Exit the worker after a few idle polls instead of polling forever.
        env["VQEC_WORKER_MAX_IDLE_POLLS"] = "3"

        try:
            server_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "vqec.server.main:app", "--port", str(port)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            healthy = False
            for _ in range(30):
                try:
                    resp = httpx.get(f"{api_url}/", timeout=1.0)
                    if resp.status_code == 200:
                        healthy = True
                        break
                except httpx.RequestError:
                    time.sleep(0.5)

            if not healthy:
                pytest.fail("FastAPI server failed to start in time.")

            config = {
                "name": f"e2e_test_{uuid.uuid4()}",
                "circuit": {
                    "type": "stim_circuit_constructor",
                    "params": {
                        "name": "surface_code:rotated_memory_z",
                        "distance": [3],
                        "rounds": [3],
                    },
                },
                "noise": {
                    "type": "depolarizing_noise",
                    "params": {"p": [0.01]},
                },
                "runner": {
                    "type": "stim_runner",
                    "params": {"shots": 10},
                },
                "decoder": {
                    "type": "pymatching",
                    "params": {},
                },
            }

            resp = httpx.post(f"{api_url}/tasks/experiment", json=config, timeout=10.0)
            assert resp.status_code == 200, resp.text
            exp_id = resp.json()["id"]

            worker_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "vqec",
                    "worker",
                    "run",
                    "--api-url",
                    api_url,
                    "--cores",
                    "1",
                    "--batch-size",
                    "1",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            completed = False
            deadline = time.time() + 60
            while time.time() < deadline:
                status_resp = httpx.get(f"{api_url}/tasks/experiment/{exp_id}", timeout=10.0)
                assert status_resp.status_code == 200
                data = status_resp.json()
                if data["status"] == "COMPLETED":
                    completed = True
                    _stop_process(worker_proc)
                    worker_proc = None
                    break
                if data["status"] == "FAILED":
                    pytest.fail(f"Experiment failed: {data}")
                time.sleep(1)

            if not completed:
                pytest.fail("Worker took too long to complete the experiment.")

            parquet_bytes = None
            export_deadline = time.time() + 30
            while time.time() < export_deadline:
                dl_resp = httpx.get(f"{api_url}/tasks/experiment/{exp_id}/download", timeout=10.0)
                if dl_resp.status_code == 200:
                    parquet_bytes = dl_resp.content
                    break
                if dl_resp.status_code != 202:
                    pytest.fail(f"Unexpected download response: {dl_resp.status_code} {dl_resp.text}")
                time.sleep(1)

            if parquet_bytes is None:
                pytest.fail("Parquet export did not finish in time.")

            df = pd.read_parquet(io.BytesIO(parquet_bytes))
            assert len(df) == 1
            assert df.iloc[0]["experiment_name"].startswith("e2e_test_")
            assert df.iloc[0]["circuit_distance"] == 3
            assert df.iloc[0]["noise_p"] == 0.01
            assert df.iloc[0]["shots"] == 10
            assert "logical_error_rate" in df.columns

        finally:
            _stop_process(worker_proc)
            _stop_process(server_proc)
