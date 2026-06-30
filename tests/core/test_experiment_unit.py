import json
import tempfile
from pathlib import Path

import pytest

from vqec.core.experiment import (
    DataGenerationSpec,
    DecodingSpec,
    Experiment,
    JobSpec,
    _expand_params,
    _parse_float_value,
    _parse_sweep_value,
    execute_data_generation,
    execute_decoding,
    execute_job,
)


MINIMAL_DATA_SPEC = DataGenerationSpec(
    circuit_type="stim_circuit_constructor",
    noise_type="depolarizing_noise",
    runner_type="stim_runner",
    circuit_params={"name": "surface_code:rotated_memory_z", "distance": 3, "rounds": 3},
    noise_params={"p": 0.01},
    runner_params={"shots": 10, "seed": 42},
)

MINIMAL_DECODE_SPEC = DecodingSpec(decoder_type="pymatching", decoder_params={})


def test_parse_float_value_formats():
    assert _parse_float_value(3) == 3.0
    assert _parse_float_value("1e-3") == pytest.approx(0.001)
    assert _parse_float_value("log10(-3)") == pytest.approx(0.001)


def test_parse_float_value_invalid():
    with pytest.raises(ValueError, match="Cannot parse float"):
        _parse_float_value([1, 2])


def test_parse_sweep_value_spaces_and_references():
    import numpy as np

    assert _parse_sweep_value("geomspace(1e-4, 1e-1, 3)", {}) == pytest.approx(
        np.geomspace(1e-4, 1e-1, 3).tolist(), rel=1e-6
    )
    assert _parse_sweep_value("logspace(1e-3, 1e-1, 2)", {}) == pytest.approx(
        [1e-3, 1e-1], rel=1e-3
    )
    assert _parse_sweep_value("linspace(0, 1, 3)", {}) == pytest.approx([0, 0.5, 1])
    assert _parse_sweep_value("distance", {"distance": 5}) == [5]
    assert _parse_sweep_value("plain", {}) == ["plain"]


def test_expand_params_cartesian_product():
    expanded = _expand_params({"distance": [3, 5], "rounds": "distance"})
    assert expanded == [{"distance": 3, "rounds": 3}, {"distance": 5, "rounds": 5}]


def test_experiment_from_file_variants(tmp_path):
    payload = {
        "name": "unit_test",
        "circuit": {
            "type": "stim_circuit_constructor",
            "params": {"name": "surface_code:rotated_memory_z", "distance": 3, "rounds": 3},
        },
        "noise": {"type": "depolarizing_noise", "params": {"p": 0.01}},
        "runner": {"type": "stim_runner", "params": {"shots": 10}},
        "decoder": {"type": "pymatching", "params": {}},
        "output": str(tmp_path / "out.parquet"),
    }

    yaml_path = tmp_path / "exp.yaml"
    yaml_path.write_text(
        "name: unit_test\n"
        "circuit:\n  type: stim_circuit_constructor\n  params:\n"
        "    name: surface_code:rotated_memory_z\n    distance: 3\n    rounds: 3\n"
        "noise:\n  type: depolarizing_noise\n  params:\n    p: 0.01\n"
        "runner:\n  type: stim_runner\n  params:\n    shots: 10\n"
        "decoder:\n  type: pymatching\n  params: {}\n"
        f"output: {payload['output']}\n"
    )
    json_path = tmp_path / "exp.json"
    json_path.write_text(json.dumps(payload))

    from_yaml = Experiment.from_yaml(yaml_path)
    from_json = Experiment.from_json(json_path)
    from_file_yaml = Experiment.from_file(yaml_path)
    from_file_json = Experiment.from_file(json_path)
    from_dict = Experiment.from_dict(payload)

    for exp in (from_yaml, from_json, from_file_yaml, from_file_json, from_dict):
        assert exp.config.name == "unit_test"


def test_experiment_validate_and_expand_jobs():
    exp = Experiment.from_dict(
        {
            "name": "sweep",
            "circuit": {
                "type": "stim_circuit_constructor",
                "params": {"name": "surface_code:rotated_memory_z", "distance": [3], "rounds": 3},
            },
            "noise": {"type": "depolarizing_noise", "params": {"p": [0.01]}},
            "runner": {"type": "stim_runner", "params": {"shots": 10}},
            "decoder": {"type": "pymatching", "params": {}},
        }
    )
    exp.validate_compatibility()
    jobs = exp.expand_jobs()
    assert len(jobs) == 1
    assert jobs[0].data_spec.circuit_params["distance"] == 3


def test_execute_data_generation_and_decoding(tmp_path):
    outcome = tmp_path / "outcome.pkl.gz"
    gen_metrics = execute_data_generation(MINIMAL_DATA_SPEC, outcome)
    assert gen_metrics["shots"] == 10
    assert outcome.exists()

    dec_metrics = execute_decoding(MINIMAL_DATA_SPEC, MINIMAL_DECODE_SPEC, outcome)
    assert 0.0 <= dec_metrics["logical_error_rate"] <= 1.0
    assert dec_metrics["n_errors"] >= 0


def test_execute_job_without_persisted_outcome():
    job = JobSpec(
        id="job-1",
        experiment_name="unit",
        data_spec=MINIMAL_DATA_SPEC,
        decode_spec=MINIMAL_DECODE_SPEC,
    )
    result = execute_job(job)
    assert result["shots"] == 10
    assert "logical_error_rate" in result


def test_execute_job_with_progress_bar():
    job = JobSpec(
        id="job-2",
        experiment_name="unit",
        data_spec=MINIMAL_DATA_SPEC,
        decode_spec=MINIMAL_DECODE_SPEC,
    )

    class DummyBar:
        def set_description(self, _desc):
            return None

    result = execute_job(job, pbar=DummyBar())
    assert result["shots"] == 10


def test_experiment_run_single_worker(tmp_path):
    out_path = tmp_path / "results.parquet"
    exp = Experiment.from_dict(
        {
            "name": "run_test",
            "circuit": {
                "type": "stim_circuit_constructor",
                "params": {"name": "surface_code:rotated_memory_z", "distance": 3, "rounds": 3},
            },
            "noise": {"type": "depolarizing_noise", "params": {"p": 0.01}},
            "runner": {"type": "stim_runner", "params": {"shots": 10, "seed": 1}},
            "decoder": {"type": "pymatching", "params": {}},
            "output": str(out_path),
        }
    )
    df = exp.run(num_workers=1, show_progress=False)
    assert len(df) == 1
    assert out_path.exists()


def test_experiment_run_with_progress(tmp_path):
    out_path = tmp_path / "progress.parquet"
    exp = Experiment.from_dict(
        {
            "name": "progress_test",
            "circuit": {
                "type": "stim_circuit_constructor",
                "params": {"name": "surface_code:rotated_memory_z", "distance": [3, 5], "rounds": 3},
            },
            "noise": {"type": "depolarizing_noise", "params": {"p": 0.01}},
            "runner": {"type": "stim_runner", "params": {"shots": 5, "seed": 2}},
            "decoder": {"type": "pymatching", "params": {}},
            "output": str(out_path),
        }
    )
    df = exp.run(num_workers=1, show_progress=True)
    assert len(df) == 2


def test_experiment_run_multiprocess(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    out_path = tmp_path / "multi.parquet"
    exp = Experiment.from_dict(
        {
            "name": "multi_test",
            "circuit": {
                "type": "stim_circuit_constructor",
                "params": {"name": "surface_code:rotated_memory_z", "distance": 3, "rounds": 3},
            },
            "noise": {"type": "depolarizing_noise", "params": {"p": 0.01}},
            "runner": {"type": "stim_runner", "params": {"shots": 5, "seed": 3}},
            "decoder": {"type": "pymatching", "params": {}},
            "output": str(out_path),
        }
    )

    mock_future = MagicMock()
    mock_future.result.return_value = {"shots": 5, "logical_error_rate": 0.0, "n_errors": 0}
    mock_executor = MagicMock()
    mock_executor.__enter__.return_value = mock_executor
    mock_executor.submit.return_value = mock_future

    monkeypatch.setattr(
        "vqec.core.experiment.concurrent.futures.ProcessPoolExecutor",
        lambda max_workers: mock_executor,
    )
    monkeypatch.setattr(
        "vqec.core.experiment.concurrent.futures.as_completed",
        lambda futures: futures,
    )

    df = exp.run(num_workers=2, show_progress=False)
    assert len(df) == 1
    mock_executor.submit.assert_called_once()
