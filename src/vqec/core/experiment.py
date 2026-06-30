from __future__ import annotations

import concurrent.futures
import itertools
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from qec_loss import SampleBatch

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, Field


# ── Job spec (represents one sweep point execution) ──────────────────────────


@dataclass
class DataGenerationSpec:
    circuit_type: str
    noise_type: str
    runner_type: str
    circuit_params: dict[str, Any]
    noise_params: dict[str, Any]
    runner_params: dict[str, Any]


@dataclass
class DecodingSpec:
    decoder_type: str
    decoder_params: dict[str, Any]


@dataclass
class JobSpec:
    """All information needed to execute one sweep point."""

    id: str
    experiment_name: str
    data_spec: DataGenerationSpec
    decode_spec: DecodingSpec


# ── Sweep value parsing ───────────────────────────────────────────────────────


def _parse_float_value(value: Any) -> float:
    """
    Parse a single float value from various formats:
    - scalar number → float as-is
    - "1e-3"      → float from string
    - "log10(1e-3)" → float from log10 string
    """
    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        m = re.fullmatch(r"log10\(([^)]+)\)", value.replace(" ", ""))
        if m:
            return 10 ** float(m.group(1))
        return float(value)

    raise ValueError(f"Cannot parse float from value: {value}")


def _parse_sweep_value(value: Any, context: dict[str, Any]) -> list[Any]:
    """
    Expand a single parameter value into a list of sweep points.

    Handles:
    - scalar             → [scalar]
    - list               → list as-is
    - "logspace(a,b,n)"  → np.logspace
    - "linspace(a,b,n)"  → np.linspace
    - "geomspace(a,b,n)" → np.geomspace
    - "param_name"       → reference to another already-resolved param (scalar only)
    """
    if isinstance(value, list):
        return value

    if isinstance(value, str):
        # logspace / linspace / geomspace shorthand
        m = re.fullmatch(r"(log|lin|geom)space\(([^,]+),([^,]+),(\d+)\)", value.replace(" ", ""))
        if m:
            fn = np.logspace if m.group(1) == "log" else (np.linspace if m.group(1) == "lin" else np.geomspace)
            a, b, n = _parse_float_value(m.group(2)), _parse_float_value(m.group(3)), int(m.group(4))
            if m.group(1) == "log":
                return fn(np.log10(a), np.log10(b), n).tolist()
            return fn(a, b, n).tolist()

        # reference to another param
        if value in context:
            ref = context[value]
            return [ref] if not isinstance(ref, list) else ref

        # plain string literal
        return [value]

    return [value]


def _expand_params(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Turn a dict that may contain sweep lists into a list of scalar dicts.

    E.g. {"distance": [3,5], "rounds": "distance"} →
         [{"distance":3,"rounds":3}, {"distance":5,"rounds":5}]

    Multi-axis sweeps produce the full cartesian product.
    Formula references ("rounds": "distance") are resolved after expansion.
    """
    # Separate formula references from concrete values
    formulas: dict[str, str] = {}
    concrete: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, str) and not re.fullmatch(r"(log|lin|geom)space\(.*\)", v.replace(" ", "")):
            formulas[k] = v
        else:
            concrete[k] = v

    # Expand concrete sweep axes into lists
    axes = {k: _parse_sweep_value(v, {}) for k, v in concrete.items()}

    # Cartesian product over all axes
    keys = list(axes.keys())
    product = list(itertools.product(*[axes[k] for k in keys]))

    expanded = []
    for combo in product:
        point = dict(zip(keys, combo))
        # Resolve formula references against the current point
        for fk, fv in formulas.items():
            if fv in point:
                point[fk] = point[fv]
            else:
                point[fk] = fv  # unresolved → keep as string, validator will catch it
        expanded.append(point)

    return expanded if expanded else [{}]


# ── Execution unit (top-level module function for pickle safety) ───────────────


def execute_data_generation(spec: DataGenerationSpec, outcome_path: str | Path) -> dict[str, Any]:
    """
    Run the data generation phase (circuit -> noise -> runner) and serialize outcomes.
    """
    from vqec.core.registry import circuit_registry, noise_registry, runner_registry
    import gzip
    import pickle

    t_start = time.perf_counter()

    circuit = circuit_registry.get(spec.circuit_type)(**spec.circuit_params)
    noise = noise_registry.get(spec.noise_type)(**spec.noise_params)
    runner = runner_registry.get(spec.runner_type)(**spec.runner_params)

    t0 = time.perf_counter()
    _ = circuit.build()
    t_build = time.perf_counter() - t0

    t0 = time.perf_counter()
    _ = noise.get(circuit)
    t_noise = time.perf_counter() - t0

    t0 = time.perf_counter()
    measurements = runner.run(circuit, noise)
    t_run = time.perf_counter() - t0

    result = {}

    t0 = time.perf_counter()
    p = Path(outcome_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wb") as f:
        pickle.dump(measurements, f)
    t_pickle_write = time.perf_counter() - t0

    uncompressed_size = len(pickle.dumps(measurements))
    compressed_size = p.stat().st_size

    # shots = measurements.shape[0] if hasattr(measurements, "shape") else len(measurements)
    if isinstance(measurements, np.ndarray):
        shots = measurements.shape[0]
    elif isinstance(measurements, list):
        shots = len(measurements)
    elif isinstance(measurements, SampleBatch):
        shots = measurements.measurements.shape[0]
    elif isinstance(measurements, dict) and "detectors" in measurements:
        shots = (
            measurements["detectors"].shape[0]
            if hasattr(measurements["detectors"], "shape")
            else len(measurements["detectors"])
        )
    else:
        raise ValueError(f"Unsupported measurements type: {type(measurements)}")

    result = {
        "shots": int(shots),
        "time_build_circuit_s": round(t_build, 5),
        "time_apply_noise_s": round(t_noise, 5),
        "time_runner_run_s": round(t_run, 5),
        "time_pickle_write_s": round(t_pickle_write, 5),
        "compression_ratio": compressed_size / uncompressed_size if uncompressed_size > 0 else 0,
        "outcome_file_path": str(p),
        **runner.result_metadata(),
    }
    return result


def execute_decoding(
    data_spec: DataGenerationSpec, decode_spec: DecodingSpec, outcome_path: str | Path
) -> dict[str, Any]:
    """
    Run the decoding phase on serialized outcomes.
    """
    from vqec.core.registry import circuit_registry, noise_registry, decoder_registry
    import gzip
    import pickle

    t_start = time.perf_counter()

    circuit = circuit_registry.get(data_spec.circuit_type)(**data_spec.circuit_params)
    noise = noise_registry.get(data_spec.noise_type)(**data_spec.noise_params)
    decoder = decoder_registry.get(decode_spec.decoder_type)(**decode_spec.decoder_params)

    _ = circuit.build()
    _ = noise.get(circuit)

    p = Path(outcome_path)
    with gzip.open(p, "rb") as f:
        measurements = pickle.load(f)

    t0 = time.perf_counter()
    decoder.setup(circuit, noise)
    t_setup = time.perf_counter() - t0

    try:
        t0 = time.perf_counter()
        logical_errors = decoder.decode(measurements, noise, circuit)
        t_decode = time.perf_counter() - t0

        shots = len(logical_errors)
        n_errors = int(logical_errors.sum())
        if shots != 0:
            ler = n_errors / shots
        else:
            ler = 1

        t_total = time.perf_counter() - t_start

        return {
            "logical_error_rate": float(ler),
            "n_errors": int(n_errors),
            "time_decoder_setup_s": round(t_setup, 5),
            "time_decoder_decode_s": round(t_decode, 5),
            "time_total_s": round(t_total, 5),
            **decoder.result_metadata(),
        }
    finally:
        decoder.teardown()


def execute_job(job: JobSpec, outcome_path: str | Path | None = None, pbar=None) -> dict[str, Any]:
    """
    Legacy wrapper for local sequential execution of both phases.
    """
    import tempfile

    path = outcome_path if outcome_path else Path(tempfile.gettempdir()) / f"outcome_{job.id}.pkl.gz"

    res_gen = execute_data_generation(job.data_spec, path)
    res_dec = execute_decoding(job.data_spec, job.decode_spec, path)

    if not outcome_path:
        Path(path).unlink(missing_ok=True)

    if pbar is not None:
        pbar.set_description(f"s={res_gen['shots']}, ler={res_dec['logical_error_rate']:.4f}")

    return {**res_gen, **res_dec}


# ── Experiment Configuration Schemas ──────────────────────────────────────────


class _AdapterConfig(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class ExperimentConfig(BaseModel):
    name: str
    circuit: _AdapterConfig
    noise: _AdapterConfig
    runner: _AdapterConfig
    decoder: _AdapterConfig
    job_backend: str = "local"
    output: str = "results/experiment.parquet"


class Experiment:
    """
    Parsed and validated QEC sweep experiment.
    """

    def __init__(self, config: ExperimentConfig) -> None:
        self.config = config

    @classmethod
    def from_yaml(cls, path: str | Path) -> Experiment:
        raw = yaml.safe_load(Path(path).read_text())
        config = ExperimentConfig.model_validate(raw)
        return cls(config)

    @classmethod
    def from_json(cls, path: str | Path) -> Experiment:
        import json

        raw = json.loads(Path(path).read_text())
        config = ExperimentConfig.model_validate(raw)
        return cls(config)

    @classmethod
    def from_file(cls, path: str | Path) -> Experiment:
        p = Path(path)
        if p.suffix.lower() == ".json":
            return cls.from_json(p)
        return cls.from_yaml(p)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Experiment:
        return cls(ExperimentConfig.model_validate(d))

    def validate_compatibility(self) -> None:
        """
        Instantiate one set of adapters with default/first-point params and
        run the compatibility check. Raises CompatibilityError on mismatch.
        """
        from vqec.core.registry import (
            circuit_registry,
            decoder_registry,
            noise_registry,
            runner_registry,
        )
        from vqec.core.validator import validate

        def _first(params: dict[str, Any]) -> dict[str, Any]:
            res = {}
            for k, v in params.items():
                val = v[0] if isinstance(v, list) else v
                parsed = _parse_sweep_value(val, res)
                res[k] = parsed[0] if parsed else val
            # Resolve formula/reference values (e.g., rounds: "distance")
            for k, v in res.items():
                if isinstance(v, str) and v in res:
                    res[k] = res[v]
            return res

        circuit = circuit_registry.get(self.config.circuit.type)(**_first(self.config.circuit.params))
        noise = noise_registry.get(self.config.noise.type)(**_first(self.config.noise.params))
        runner = runner_registry.get(self.config.runner.type)(**_first(self.config.runner.params))
        decoder = decoder_registry.get(self.config.decoder.type)(**_first(self.config.decoder.params))
        validate(circuit, noise, runner, decoder)

    def expand_jobs(self) -> list[JobSpec]:
        """
        Expand all parameter sweeps into a flat list of JobSpec objects.
        """
        circuit_points = _expand_params(self.config.circuit.params)
        noise_points = _expand_params(self.config.noise.params)
        decoder_points = _expand_params(self.config.decoder.params)

        runner_point = {k: v for k, v in self.config.runner.params.items()}

        jobs: list[JobSpec] = []
        for cp in circuit_points:
            for np_ in noise_points:
                for dp in decoder_points:
                    jobs.append(
                        JobSpec(
                            id=str(uuid.uuid4()),
                            experiment_name=self.config.name,
                            data_spec=DataGenerationSpec(
                                circuit_type=self.config.circuit.type,
                                noise_type=self.config.noise.type,
                                runner_type=self.config.runner.type,
                                circuit_params=cp,
                                noise_params=np_,
                                runner_params=runner_point,
                            ),
                            decode_spec=DecodingSpec(
                                decoder_type=self.config.decoder.type,
                                decoder_params=dp,
                            ),
                        )
                    )
        return jobs

    def run(self, num_workers: int | None = None, show_progress: bool = True) -> pd.DataFrame:
        """
        Execute all expanded jobs and return results as a Pandas DataFrame.
        Automatically saves to Parquet if specified in config.output.
        """
        self.validate_compatibility()
        jobs = self.expand_jobs()

        workers = num_workers if num_workers is not None else 1

        if workers > 1:
            results = [None] * len(jobs)
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
                future_to_idx = {executor.submit(execute_job, job): i for i, job in enumerate(jobs)}

                if show_progress:
                    from tqdm import tqdm

                    with tqdm(total=len(jobs), desc="Jobs", position=0) as pbar:
                        for future in concurrent.futures.as_completed(future_to_idx):
                            idx = future_to_idx[future]
                            results[idx] = future.result()
                            pbar.update(1)
                else:
                    for future in concurrent.futures.as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        results[idx] = future.result()
        else:
            if show_progress and len(jobs) > 1:
                from tqdm import tqdm

                results = []
                with tqdm(total=len(jobs), desc="Jobs", position=0) as pbar:
                    for job in jobs:
                        res = execute_job(job, pbar=pbar)
                        pbar.update(1)
                        results.append(res)
            else:
                results = [execute_job(j) for j in jobs]

        # Flat map results
        rows = []
        for job, res in zip(jobs, results):
            row = {
                "experiment_name": job.experiment_name,
                "circuit_type": job.data_spec.circuit_type,
                "noise_type": job.data_spec.noise_type,
                "runner_type": job.data_spec.runner_type,
                "decoder_type": job.decode_spec.decoder_type,
                **{f"circuit_{k}": v for k, v in job.data_spec.circuit_params.items()},
                **{f"noise_{k}": v for k, v in job.data_spec.noise_params.items()},
                **{f"runner_{k}": v for k, v in job.data_spec.runner_params.items()},
                **{f"decoder_{k}": v for k, v in job.decode_spec.decoder_params.items()},
                **res,
            }
            rows.append(row)

        df = pd.DataFrame(rows)

        # Save to Parquet
        if self.config.output:
            out_path = Path(self.config.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(out_path, index=False)

        return df

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Experiment '{self.config.name}'>"
