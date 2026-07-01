"""End-to-end test: real server process + real Dask cluster."""

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
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def test_full_distributed_e2e():
    """
    1. Spawn a Dask scheduler and worker.
    2. Spawn the FastAPI server in a background process connected to the scheduler.
    3. Submit a valid experiment via HTTP.
    4. Wait for the experiment to reach DONE.
    5. Download Parquet results and verify contents.
    6. Submit an invalid experiment, wait for ERROR.
    7. Submit the first experiment again to test cache hit (should be very fast).
    """
    dask_port = _free_port()
    api_port = _free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    scheduler_url = f"tcp://127.0.0.1:{dask_port}"

    scheduler_proc = None
    worker_proc = None
    server_proc = None

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "e2e_test.db")
        env = os.environ.copy()
        env["VQEC_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        env["VQEC_STORAGE_DIR"] = temp_dir
        env["VQEC_DASK_SCHEDULER_ADDRESS"] = scheduler_url

        try:
            # 1. Start Dask Scheduler
            scheduler_proc = subprocess.Popen(
                [sys.executable, "-m", "distributed.cli.dask_scheduler", "--port", str(dask_port)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )

            # 2. Start Dask Worker
            worker_proc = subprocess.Popen(
                [sys.executable, "-m", "distributed.cli.dask_worker", scheduler_url, "--preload", "vqec.dask_preload"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )

            # Wait for Dask to be ready
            time.sleep(3)

            # 3. Start FastAPI Server
            server_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "vqec.server.main:app", "--port", str(api_port)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
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

            # 4. Valid Experiment
            config_valid = {
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

            resp = httpx.post(f"{api_url}/tasks/experiment", json=config_valid, timeout=10.0)
            assert resp.status_code == 200, resp.text
            exp_id_1 = resp.json()["id"]

            def wait_for_status(exp_id, expected_status, timeout_sec=60):
                deadline = time.time() + timeout_sec
                while time.time() < deadline:
                    status_resp = httpx.get(f"{api_url}/tasks/experiment/{exp_id}", timeout=10.0)
                    assert status_resp.status_code == 200
                    data = status_resp.json()
                    if data["status"] == expected_status:
                        return True
                    if expected_status == "DONE" and data["status"] == "ERROR":
                        pytest.fail(f"Experiment failed unexpectedly: {data}")
                    time.sleep(1)
                return False

            if not wait_for_status(exp_id_1, "DONE"):
                pytest.fail("Worker took too long to complete the experiment.")

            # 5. Download and verify Parquet
            parquet_bytes = None
            export_deadline = time.time() + 30
            while time.time() < export_deadline:
                dl_resp = httpx.get(f"{api_url}/tasks/experiment/{exp_id_1}/download", timeout=10.0)
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
            assert df.iloc[0]["runner_shots"] == 10
            assert "logical_error_rate" in df.columns

            # 6. Invalid Experiment (should fail at task execution, not 422)
            config_invalid = {
                "name": f"e2e_invalid_{uuid.uuid4()}",
                "circuit": {
                    "type": "stim_circuit_constructor",
                    "params": {
                        "name": "invalid_stim_circuit_name_does_not_exist",
                        "distance": [3],
                        "rounds": [3],
                    },
                },
                "noise": config_valid["noise"],
                "runner": config_valid["runner"],
                "decoder": config_valid["decoder"],
            }
            resp2 = httpx.post(f"{api_url}/tasks/experiment", json=config_invalid, timeout=10.0)
            assert resp2.status_code == 200, resp2.text
            exp_id_2 = resp2.json()["id"]

            if not wait_for_status(exp_id_2, "ERROR"):
                pytest.fail("Invalid experiment did not reach ERROR status in time.")

            # 7. Cache Hit (Submit first experiment again)
            t0 = time.time()
            resp3 = httpx.post(f"{api_url}/tasks/experiment", json=config_valid, timeout=10.0)
            assert resp3.status_code == 200
            exp_id_3 = resp3.json()["id"]
            
            # Since it's fully cached, it should resolve extremely fast without re-running tasks.
            # Dask will just pass through the cached results.
            if not wait_for_status(exp_id_3, "DONE", timeout_sec=15):
                pytest.fail("Cached experiment took too long.")
            t1 = time.time()
            # Assert the second run was reasonably fast
            assert (t1 - t0) < 15, "Cache hit was unexpectedly slow"

        finally:
            _stop_process(server_proc)
            _stop_process(worker_proc)
            _stop_process(scheduler_proc)
