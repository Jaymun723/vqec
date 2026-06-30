import pytest
import sys
import os
import signal
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from vqec.cli.main import main

@patch("uvicorn.run")
def test_cli_server(mock_uvicorn_run):
    test_args = ["vqec", "server", "--host", "0.0.0.0", "--port", "9000", "--reload"]
    with patch.object(sys, "argv", test_args):
        main()
    mock_uvicorn_run.assert_called_once_with(
        "vqec.server.main:app", 
        host="0.0.0.0", 
        port=9000, 
        reload=True
    )

@patch("vqec.worker.worker_loop")
def test_cli_worker_run(mock_worker_loop):
    test_args = [
        "vqec", "worker", "run", 
        "--api-url", "http://test:1234", 
        "--cores", "4",
        "--batch-size", "20",
        "--has-gpu"
    ]
    with patch.object(sys, "argv", test_args):
        main()
    mock_worker_loop.assert_called_once_with(
        api_url="http://test:1234",
        cores=4,
        has_gpu=True,
        batch_size=20
    )

@patch("vqec.worker.worker_loop")
def test_cli_worker_run_default_batch(mock_worker_loop):
    test_args = [
        "vqec", "worker", "run", 
        "--api-url", "http://test:1234", 
        "--cores", "4"
    ]
    with patch.object(sys, "argv", test_args):
        main()
    mock_worker_loop.assert_called_once_with(
        api_url="http://test:1234",
        cores=4,
        has_gpu=False,
        batch_size=10
    )

@patch("sys.exit", side_effect=SystemExit)
def test_cli_worker_deploy_invalid(mock_exit):
    test_args = ["vqec", "worker", "deploy", "-n", "0"]
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit):
            main()

@patch("subprocess.Popen")
@patch("vqec.cli.main.Path.mkdir")
@patch("builtins.open")
def test_cli_worker_deploy(mock_open, mock_mkdir, mock_popen):
    mock_process = MagicMock()
    mock_process.pid = 999
    mock_popen.return_value = mock_process
    
    test_args = [
        "vqec", "worker", "deploy", 
        "-n", "2", 
        "--api-url", "http://test:1234", 
        "--cores", "2",
        "--has-gpu"
    ]
    
    with patch.object(sys, "argv", test_args):
        with patch("vqec.cli.main.Path.exists", return_value=True):
            from unittest.mock import mock_open
            m_open = mock_open(read_data="123\n")
            with patch("builtins.open", m_open):
                main()
            
    assert mock_popen.call_count == 2
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

@patch("os.kill")
@patch("vqec.cli.main.Path.unlink")
def test_cli_worker_stop(mock_unlink, mock_kill):
    test_args = ["vqec", "worker", "stop"]
    
    with patch.object(sys, "argv", test_args):
        with patch("vqec.cli.main.Path.exists", return_value=True):
            from unittest.mock import mock_open
            m_open = mock_open(read_data="123\n456\n789\n")
            with patch("builtins.open", m_open):
                # mock os.kill behavior
                mock_kill.side_effect = [None, ProcessLookupError, Exception("test")]
                main()
                
    mock_kill.assert_has_calls([
        call(123, signal.SIGTERM),
        call(456, signal.SIGTERM),
        call(789, signal.SIGTERM)
    ])
    mock_unlink.assert_called_once_with(missing_ok=True)

@patch("os.kill")
@patch("vqec.cli.main.Path.unlink")
def test_cli_worker_stop_forceful(mock_unlink, mock_kill):
    test_args = ["vqec", "worker", "stop", "--forceful"]
    with patch.object(sys, "argv", test_args):
        with patch("vqec.cli.main.Path.exists", return_value=True):
            from unittest.mock import mock_open
            m_open = mock_open(read_data="123\n")
            with patch("builtins.open", m_open):
                main()
    mock_kill.assert_called_with(123, signal.SIGKILL)

def test_cli_worker_stop_no_file():
    test_args = ["vqec", "worker", "stop"]
    with patch.object(sys, "argv", test_args):
        with patch("vqec.cli.main.Path.exists", return_value=False):
            main()

@patch("vqec.cli.main.Path.exists", return_value=True)
def test_cli_worker_clear_logs(mock_exists):
    test_args = ["vqec", "worker", "clear-logs"]
    
    mock_file1 = MagicMock()
    mock_file1.name = "worker_1.log"
    mock_file2 = MagicMock()
    mock_file2.name = "worker_2.log"
    mock_file2.unlink.side_effect = Exception("test error")
    
    with patch.object(sys, "argv", test_args):
        with patch("vqec.cli.main.Path.glob", return_value=[mock_file1, mock_file2]):
            main()
            
    mock_file1.unlink.assert_called_once()
    mock_file2.unlink.assert_called_once()

@patch("vqec.cli.main.Path.exists", return_value=False)
def test_cli_worker_clear_logs_no_dir(mock_exists):
    with patch.object(sys, "argv", ["vqec", "worker", "clear-logs"]):
        main()

@patch("vqec.cli.main.Path.exists", return_value=True)
def test_cli_worker_clear_logs_no_files(mock_exists):
    with patch.object(sys, "argv", ["vqec", "worker", "clear-logs"]):
        with patch("vqec.cli.main.Path.glob", return_value=[]):
            main()

@patch("sys.exit", side_effect=SystemExit)
def test_cli_no_args(mock_exit):
    with patch.object(sys, "argv", ["vqec"]):
        with pytest.raises(SystemExit):
            main()
    mock_exit.assert_called_once_with(1)

@patch("sys.exit", side_effect=SystemExit)
def test_cli_worker_no_command(mock_exit):
    with patch.object(sys, "argv", ["vqec", "worker"]):
        with pytest.raises(SystemExit):
            main()
    mock_exit.assert_called_once_with(1)
