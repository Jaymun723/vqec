import pytest
import sys
from unittest.mock import patch

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

@patch("sys.exit", side_effect=SystemExit)
def test_cli_no_args(mock_exit):
    with patch.object(sys, "argv", ["vqec"]):
        with pytest.raises(SystemExit):
            main()
    mock_exit.assert_called_once_with(1)
