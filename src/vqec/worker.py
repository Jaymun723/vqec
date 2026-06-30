import concurrent.futures
import json
import logging
import os
import tempfile
import time
import threading
from typing import Any
import httpx

from vqec.core.experiment import DataGenerationSpec, DecodingSpec, execute_data_generation, execute_decoding

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vqec-worker")

active_tasks = set()
active_tasks_lock = threading.Lock()

# Per-thread heartbeat client (works across processes due to thread-local storage)


def _load_adapters() -> None:
    from pathlib import Path

    from vqec.core.registry import scan_adapters

    scan_adapters(Path(__file__).parent / "adapters")


def _init_worker_process() -> None:
    _load_adapters()


def _max_idle_polls() -> int | None:
    raw = os.environ.get("VQEC_WORKER_MAX_IDLE_POLLS")
    if not raw:
        return None
    return int(raw)


_heartbeat_client_local = threading.local()


def _get_heartbeat_client(api_url: str) -> httpx.Client:
    """Get or create a per-thread heartbeat client with appropriate pool limits.

    Each worker process will have its own client, and each heartbeat thread
    within a process will have its own client instance.
    """
    client = getattr(_heartbeat_client_local, "client", None)
    if client is None:
        client = httpx.Client(
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=8), timeout=httpx.Timeout(10.0)
        )
        _heartbeat_client_local.client = client
    return client


def _close_heartbeat_client() -> None:
    """Close the per-thread heartbeat client if it exists."""
    client = getattr(_heartbeat_client_local, "client", None)
    if client is not None:
        client.close()
        _heartbeat_client_local.client = None


def heartbeat_loop(api_url: str, interval: float = 60):
    heartbeat_client = _get_heartbeat_client(api_url)
    while True:
        time.sleep(interval)
        with active_tasks_lock:
            task_ids = list(active_tasks)
        if not task_ids:
            continue
        try:
            resp = heartbeat_client.post(f"{api_url}/worker/heartbeat", json={"task_ids": task_ids}, timeout=10.0)
            if resp.status_code == 404:
                logger.warning(
                    "Heartbeat returned 404 — lease lost or task not found for %s. "
                    "Clearing active task tracking; in-flight subprocess work may still "
                    "finish harmlessly (upload/complete are idempotent on the server).",
                    task_ids,
                )
                with active_tasks_lock:
                    active_tasks.difference_update(task_ids)
            else:
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")


def run_task(api_url: str, task: dict[str, Any]) -> None:
    task_type = task["type"]
    task_id = task["id"]
    spec_dict = task["spec"]

    try:
        if task_type == "data_generation":
            logger.info(f"Starting DataGenerationTask {task_id}")
            data_spec = DataGenerationSpec(**spec_dict)

            with tempfile.NamedTemporaryFile(suffix=".pkl.gz", delete=False) as tmp:
                temp_path = tmp.name

            try:
                metrics = execute_data_generation(data_spec, temp_path)

                # Use dedicated client for upload with higher timeout for large files
                with httpx.Client(
                    limits=httpx.Limits(max_connections=64), timeout=httpx.Timeout(600.0, read=600.0)
                ) as client:
                    with open(temp_path, "rb") as f:
                        files = {"file": (f"{task_id}.pkl.gz", f, "application/gzip")}
                        data = {"shots": str(metrics.pop("shots")), "metrics_json": json.dumps(metrics)}
                        resp = client.post(f"{api_url}/worker/upload/{task_id}", files=files, data=data)
                        resp.raise_for_status()
                logger.info(f"Completed DataGenerationTask {task_id}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        elif task_type == "decoding":
            logger.info(f"Starting DecodingTask {task_id}")
            data_id = task["data_id"]
            decode_spec = DecodingSpec(**spec_dict)
            data_spec = DataGenerationSpec(**task.get("data_spec", {}))

            with tempfile.NamedTemporaryFile(suffix=".pkl.gz", delete=False) as tmp:
                temp_path = tmp.name

            try:
                # Use a dedicated client with larger connection pool for raw performance
                with httpx.Client(
                    limits=httpx.Limits(max_connections=128, max_keepalive_connections=32),
                    timeout=httpx.Timeout(300.0, read=300.0),
                ) as client:
                    with client.stream("GET", f"{api_url}/worker/download/{data_id}") as resp:
                        resp.raise_for_status()
                        with open(temp_path, "wb") as f:
                            for chunk in resp.iter_bytes():
                                f.write(chunk)

                metrics = execute_decoding(data_spec, decode_spec, temp_path)

                payload = {"type": "decoding", "id": task_id, "status": "COMPLETED", "metrics": metrics}
                # Use heartbeat client for complete request
                heartbeat_client = _get_heartbeat_client(api_url)
                resp = heartbeat_client.post(f"{api_url}/worker/complete", json=payload, timeout=10.0)
                resp.raise_for_status()
                logger.info(f"Completed DecodingTask {task_id}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    except Exception as e:
        logger.error(f"Task {task_type} {task_id} failed: {e}", exc_info=True)
        payload = {"type": task_type, "id": task_id, "status": "FAILED", "error_message": str(e)}
        try:
            heartbeat_client = _get_heartbeat_client(api_url)
            heartbeat_client.post(f"{api_url}/worker/complete", json=payload, timeout=10.0)
        except Exception as api_err:
            logger.error(f"Failed to report error to API: {api_err}")


def worker_loop(api_url: str, cores: int, has_gpu: bool, batch_size: int):
    _load_adapters()

    logger.info(f"Starting VQEC worker connecting to {api_url}")
    logger.info(f"Cores: {cores}, GPU: {has_gpu}, Batch Size: {batch_size}")

    hb_thread = threading.Thread(target=heartbeat_loop, args=(api_url,), daemon=True)
    hb_thread.start()

    max_idle_polls = _max_idle_polls()
    idle_polls = 0

    # Create a dedicated client for main thread polling
    poll_client = httpx.Client(
        limits=httpx.Limits(max_connections=16, max_keepalive_connections=4), timeout=httpx.Timeout(10.0)
    )

    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=cores, initializer=_init_worker_process) as executor:
            while True:
                try:
                    resp = poll_client.post(
                        f"{api_url}/worker/poll", json={"batch_size": batch_size, "has_gpu": has_gpu}, timeout=10.0
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    tasks = data.get("tasks", [])

                    if not tasks:
                        idle_polls += 1
                        if max_idle_polls is not None and idle_polls >= max_idle_polls:
                            logger.info("No tasks after %d idle polls; exiting worker.", idle_polls)
                            break
                        time.sleep(2)
                        continue

                    idle_polls = 0
                    logger.info(f"Fetched {len(tasks)} tasks.")

                    with active_tasks_lock:
                        for t in tasks:
                            active_tasks.add(t["id"])

                    future_to_task = {}
                    for task in tasks:
                        future = executor.submit(run_task, api_url, task)
                        future_to_task[future] = task["id"]

                    for future in concurrent.futures.as_completed(future_to_task):
                        tid = future_to_task[future]
                        with active_tasks_lock:
                            active_tasks.discard(tid)
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f"Exception in future result: {e}")

                except httpx.RequestError as e:
                    logger.warning(f"Failed to connect to {api_url}: {e}. Retrying in 5 seconds...")
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"Worker loop error: {e}", exc_info=True)
                    time.sleep(5)
    finally:
        poll_client.close()
