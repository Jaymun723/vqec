import pytest
import json
from unittest.mock import patch, MagicMock, call
import tempfile
import os

from vqec.worker import run_task

@patch("vqec.worker.execute_data_generation")
@patch("vqec.worker.httpx.post")
def test_run_data_generation_task(mock_post, mock_execute):
    mock_execute.return_value = {"shots": 1000, "time_total": 0.5}
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    task = {
        "type": "data_generation",
        "id": 123,
        "spec": {
            "circuit_type": "stim_circuit_constructor",
            "noise_type": "depolarizing_noise",
            "runner_type": "stim_runner",
            "circuit_params": {"name": "c", "distance": 3, "rounds": 3},
            "noise_params": {"p": 0.01},
            "runner_params": {"shots": 1000}
        }
    }

    run_task("http://localhost:8000", task)

    mock_execute.assert_called_once()
    mock_post.assert_called_once()

@patch("vqec.worker.execute_decoding")
@patch("vqec.worker.httpx.stream")
@patch("vqec.worker.httpx.post")
def test_run_decoding_task(mock_post, mock_stream, mock_execute):
    mock_execute.return_value = {"logical_error_rate": 0.01, "time_total_s": 0.5}
    
    mock_stream_ctx = MagicMock()
    mock_stream_response = MagicMock()
    mock_stream_response.raise_for_status.return_value = None
    mock_stream_response.iter_bytes.return_value = [b"fake", b"data"]
    mock_stream_ctx.__enter__.return_value = mock_stream_response
    mock_stream.return_value = mock_stream_ctx

    mock_post_response = MagicMock()
    mock_post_response.raise_for_status.return_value = None
    mock_post.return_value = mock_post_response

    task = {
        "type": "decoding",
        "id": 456,
        "data_id": 123,
        "spec": {
            "decoder_type": "pymatching",
            "decoder_params": {}
        },
        "data_spec": {
            "circuit_type": "stim_circuit_constructor",
            "noise_type": "depolarizing_noise",
            "runner_type": "stim_runner",
            "circuit_params": {"name": "c", "distance": 3, "rounds": 3},
            "noise_params": {"p": 0.01},
            "runner_params": {"shots": 1000}
        }
    }

    run_task("http://localhost:8000", task)

    mock_execute.assert_called_once()
    mock_post.assert_called_once()


@patch("vqec.worker.httpx.post")
def test_run_task_failure(mock_post):
    mock_post_response = MagicMock()
    mock_post_response.raise_for_status.return_value = None
    mock_post.return_value = mock_post_response

    task = {
        "type": "data_generation",
        "id": 789,
        "spec": {} # Missing required fields
    }

    run_task("http://localhost:8000", task)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:8000/worker/complete"
    assert kwargs["json"]["type"] == "data_generation"
    assert kwargs["json"]["status"] == "FAILED"

@patch("vqec.worker.httpx.post", side_effect=Exception("api failure"))
def test_run_task_failure_api_down(mock_post):
    task = {
        "type": "data_generation",
        "id": 789,
        "spec": {} 
    }
    run_task("http://localhost:8000", task)
    # The API call to report failure will raise Exception but it should be caught and logged.
    mock_post.assert_called_once()

@patch("vqec.worker.httpx.post")
def test_heartbeat_loop_404(mock_post):
    import vqec.worker

    vqec.worker.active_tasks.add(123)

    mock_post_response = MagicMock()
    mock_post_response.status_code = 404
    mock_post.return_value = mock_post_response

    with patch("vqec.worker.time.sleep", side_effect=[None, KeyboardInterrupt]):
        try:
            vqec.worker.heartbeat_loop("http://localhost:8000", interval=0)
        except KeyboardInterrupt:
            pass

    assert mock_post.call_count == 1
    assert 123 not in vqec.worker.active_tasks
    vqec.worker.active_tasks.clear()

@patch("vqec.worker.httpx.post")
def test_heartbeat_loop_exception(mock_post):
    import vqec.worker

    vqec.worker.active_tasks.add(123)

    mock_post.side_effect = Exception("error")

    with patch("vqec.worker.time.sleep", side_effect=[None, KeyboardInterrupt]):
        try:
            vqec.worker.heartbeat_loop("http://localhost:8000", interval=0)
        except KeyboardInterrupt:
            pass

    assert mock_post.call_count == 1
    vqec.worker.active_tasks.clear()

@patch("vqec.worker.time.sleep", side_effect=KeyboardInterrupt)
def test_heartbeat_loop_no_tasks(_mock_sleep):
    import vqec.worker
    with pytest.raises(KeyboardInterrupt):
        vqec.worker.heartbeat_loop("http://localhost:8000", interval=0)

@patch("vqec.worker.httpx.post")
def test_heartbeat_loop(mock_post):
    import vqec.worker

    vqec.worker.active_tasks.add(123)
    vqec.worker.active_tasks.add(456)

    mock_post_response = MagicMock()
    mock_post_response.status_code = 200
    mock_post.return_value = mock_post_response

    with patch("vqec.worker.time.sleep", side_effect=[None, KeyboardInterrupt]):
        try:
            vqec.worker.heartbeat_loop("http://localhost:8000", interval=0)
        except KeyboardInterrupt:
            pass

    assert mock_post.call_count == 1

    vqec.worker.active_tasks.clear()

@patch("vqec.worker.httpx.post")
def test_heartbeat_loop_skips_without_active_tasks(mock_post):
    import vqec.worker

    with patch("vqec.worker.time.sleep", side_effect=[None, KeyboardInterrupt]):
        try:
            vqec.worker.heartbeat_loop("http://localhost:8000", interval=0)
        except KeyboardInterrupt:
            pass

    mock_post.assert_not_called()


def test_init_worker_process_loads_adapters():
    import vqec.worker
    from vqec.core.registry import circuit_registry

    vqec.worker._init_worker_process()
    assert "stim_circuit_constructor" in circuit_registry.all()


@patch.dict(os.environ, {"VQEC_WORKER_MAX_IDLE_POLLS": "2"})
@patch("vqec.worker.httpx.post")
@patch("vqec.worker.time.sleep")
@patch("vqec.worker.concurrent.futures.ProcessPoolExecutor")
@patch("vqec.worker.threading.Thread")
def test_worker_loop_exits_on_idle(mock_thread, mock_executor, mock_sleep, mock_post):
    import vqec.worker

    mock_executor_instance = MagicMock()
    mock_executor_instance.__enter__.return_value = mock_executor_instance
    mock_executor.return_value = mock_executor_instance

    mock_empty = MagicMock()
    mock_empty.json.return_value = {"tasks": []}
    mock_post.return_value = mock_empty

    vqec.worker.worker_loop("http://localhost:8000", 1, False, 1)

    assert mock_post.call_count == 2

@patch("vqec.worker.httpx.post")
@patch("vqec.worker.time.sleep")
@patch("vqec.worker.concurrent.futures.ProcessPoolExecutor")
@patch("vqec.worker.threading.Thread")
def test_worker_loop_full(mock_thread, mock_executor, mock_sleep, mock_post):
    import httpx
    import vqec.worker
    # Mock executor
    mock_executor_instance = MagicMock()
    mock_executor_instance.__enter__.return_value = mock_executor_instance
    mock_executor.return_value = mock_executor_instance
    
    mock_empty = MagicMock()
    mock_empty.json.return_value = {"tasks": []}
    
    mock_tasks = MagicMock()
    mock_tasks.json.return_value = {"tasks": [{"id": 1, "type": "data_generation", "spec": {}}]}
    
    mock_post.side_effect = [
        mock_empty, # Test sleep when no tasks
        httpx.RequestError("test err"), # Test RequestError
        Exception("generic err"), # Test generic Exception
        mock_tasks, # Valid tasks
        KeyboardInterrupt()
    ]
    
    mock_future = MagicMock()
    mock_future.result.side_effect = [Exception("future fail"), None]
    mock_executor_instance.submit.return_value = mock_future
    
    with patch("vqec.worker.concurrent.futures.as_completed", return_value=[mock_future]):
        try:
            from vqec.worker import worker_loop
            worker_loop("http://localhost:8000", 2, False, 10)
        except KeyboardInterrupt:
            pass
            
    mock_executor.assert_called_once_with(max_workers=2, initializer=vqec.worker._init_worker_process)
    assert mock_post.call_count == 5
