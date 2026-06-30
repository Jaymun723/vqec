import runpy
import sys
from unittest.mock import patch

import pytest


def test_vqec_package_main():
    with patch("vqec.cli.main.main") as mock_main, patch.object(sys, "argv", ["vqec"]):
        runpy.run_module("vqec", run_name="__main__")
    mock_main.assert_called_once()


def test_vqec_cli_module_main():
    with patch.object(sys, "argv", ["vqec"]):
        with pytest.raises(SystemExit) as exc:
            runpy.run_module("vqec.cli.main", run_name="__main__")
    assert exc.value.code == 1


def test_vqec_version():
    import vqec

    assert vqec.__version__ == "0.1.0"


def test_vqec_module_version_flag():
    with patch.object(sys, "argv", ["vqec", "--version"]):
        with pytest.raises(SystemExit) as exc:
            runpy.run_module("vqec", run_name="__main__")
    assert exc.value.code == 0
