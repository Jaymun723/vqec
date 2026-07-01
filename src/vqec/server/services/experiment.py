import json
import asyncio
import traceback
from pathlib import Path
from dask.distributed import Client, Future
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select as sqlmodel_select

from vqec.core.experiment import Experiment as CoreExperiment, ExperimentConfig
from vqec.core.validator import CompatibilityError
from vqec.server.models.db import Experiment, DataCache, DecodeCache, TaskStatus
from vqec.server.models.schemas import ExperimentRead, ExperimentDetail
from vqec.server.repositories.experiment import ExperimentRepository
from vqec.server.utils import compute_config_hash
from vqec.server.config import settings

_active_experiments: dict[int, Future] = {}

def get_dask_client():
    from vqec.server.main import dask_client
    return dask_client

def wrap_data_generation(spec, data_hash):
    from vqec.core.experiment import execute_data_generation
    from pathlib import Path
    import os, json
    from sqlalchemy import create_engine, text
    
    storage_dir = Path(os.environ.get("VQEC_STORAGE_DIR", "data/storage"))
    out_path = storage_dir / "data" / f"{data_hash}.pkl.gz"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    metrics = execute_data_generation(spec, out_path)
    
    db_url = os.environ.get("VQEC_DATABASE_URL", "sqlite:///data/vqec_server.db").replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(db_url, connect_args={"timeout": 30})
    with engine.begin() as conn:
        conn.execute(
            text("INSERT OR IGNORE INTO data_cache (task_hash, output_path, metadata_json) VALUES (:hash, :path, :meta)"),
            {"hash": data_hash, "path": str(out_path), "meta": json.dumps(metrics)}
        )
    return {"outcome_file_path": str(out_path), "metadata_json": metrics}

def wrap_decoding(data_spec, decode_spec, decode_hash, data_res):
    from vqec.core.experiment import execute_decoding
    import os, json
    from sqlalchemy import create_engine, text
    
    metrics = execute_decoding(data_spec, decode_spec, data_res["outcome_file_path"])
    
    db_url = os.environ.get("VQEC_DATABASE_URL", "sqlite:///data/vqec_server.db").replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(db_url, connect_args={"timeout": 30})
    with engine.begin() as conn:
        conn.execute(
            text("INSERT OR IGNORE INTO decode_cache (task_hash, metadata_json) VALUES (:hash, :meta)"),
            {"hash": decode_hash, "meta": json.dumps(metrics)}
        )
    return metrics

def wrap_consolidation(jobs, decode_results, config_output):
    import pandas as pd
    from pathlib import Path
    import os
    
    storage_dir = Path(os.environ.get("VQEC_STORAGE_DIR", "data/storage"))
    
    rows = []
    for job, res in zip(jobs, decode_results):
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
    out_path = Path(config_output) if Path(config_output).is_absolute() else storage_dir / config_output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return str(out_path)

def _on_consolidation_done(future, experiment_id, db_url):
    import os
    from sqlalchemy import create_engine, text
    import traceback
    
    url = db_url.replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(url, connect_args={"timeout": 30})
    
    try:
        result_path = future.result()
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE experiment SET status = :status, result_path = :path WHERE id = :id"),
                {"status": TaskStatus.DONE.value, "path": result_path, "id": experiment_id}
            )
    except Exception as e:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE experiment SET status = :status, error = :error WHERE id = :id"),
                {"status": TaskStatus.ERROR.value, "error": str(e) + "\n" + traceback.format_exc(), "id": experiment_id}
            )
    
    _active_experiments.pop(experiment_id, None)

class ExperimentService:
    def __init__(self, session: AsyncSession):
        self.repo = ExperimentRepository(session)
        self.session = session
        self.dask_client = get_dask_client()

    async def to_read(self, experiment: Experiment) -> ExperimentRead:
        return ExperimentRead(
            id=experiment.id,
            name=experiment.name,
            config_hash=experiment.config_hash,
            status=experiment.status,
            error=experiment.error,
            result_path=experiment.result_path,
            submitted_at=experiment.submitted_at,
        )

    async def to_detail(self, experiment: Experiment) -> ExperimentDetail:
        summary = await self.to_read(experiment)
        return ExperimentDetail(
            **summary.model_dump(),
            config=json.loads(experiment.config_json)
        )

    async def _launch_graph(self, experiment: Experiment, config_dict: dict):
        config = ExperimentConfig.model_validate(config_dict)
        experiment_model = CoreExperiment(config)
        jobs = experiment_model.expand_jobs()

        data_futures = {}
        decode_futures = []
        
        data_cache_objs = (await self.session.execute(sqlmodel_select(DataCache))).scalars().all()
        data_cache = {obj.task_hash: {"outcome_file_path": obj.output_path, "metadata_json": json.loads(obj.metadata_json)} for obj in data_cache_objs}
        
        decode_cache_objs = (await self.session.execute(sqlmodel_select(DecodeCache))).scalars().all()
        decode_cache = {obj.task_hash: json.loads(obj.metadata_json) for obj in decode_cache_objs}

        for job in jobs:
            data_spec_dict = {
                "circuit_type": job.data_spec.circuit_type,
                "noise_type": job.data_spec.noise_type,
                "runner_type": job.data_spec.runner_type,
                "circuit_params": job.data_spec.circuit_params,
                "noise_params": job.data_spec.noise_params,
                "runner_params": job.data_spec.runner_params,
            }
            data_hash = compute_config_hash(data_spec_dict)

            if data_hash in data_futures:
                dfuture = data_futures[data_hash]
            else:
                if data_hash in data_cache:
                    dfuture = self.dask_client.submit(lambda x: x, data_cache[data_hash], pure=False)
                else:
                    dfuture = self.dask_client.submit(wrap_data_generation, job.data_spec, data_hash, pure=False, key=f"data_{data_hash}")
                data_futures[data_hash] = dfuture

            decode_spec_dict = {
                "data_hash": data_hash,
                "decoder_type": job.decode_spec.decoder_type,
                "decoder_params": job.decode_spec.decoder_params,
            }
            decode_hash = compute_config_hash(decode_spec_dict)
            
            if decode_hash in decode_cache:
                dec_future = self.dask_client.submit(lambda x: x, decode_cache[decode_hash], pure=False)
            else:
                dec_future = self.dask_client.submit(wrap_decoding, job.data_spec, job.decode_spec, decode_hash, dfuture, pure=False, key=f"decode_{decode_hash}")
            decode_futures.append(dec_future)

        consolidation_future = self.dask_client.submit(wrap_consolidation, jobs, decode_futures, config.output, pure=False, key=f"consolidate_{experiment.id}")
        consolidation_future.add_done_callback(lambda f: _on_consolidation_done(f, experiment.id, settings.database_url))
        _active_experiments[experiment.id] = consolidation_future

    async def submit_experiment(self, config_dict: dict) -> Experiment:
        config_hash = compute_config_hash(config_dict)

        existing = await self.repo.get_by_hash(config_hash)
        if existing:
            if existing.status == TaskStatus.IN_FLIGHT and existing.id not in _active_experiments:
                existing.status = TaskStatus.ERROR
                self.session.add(existing)
                await self.session.commit()
            return existing

        try:
            config = ExperimentConfig.model_validate(config_dict)
            experiment_model = CoreExperiment(config)
            experiment_model.validate_compatibility()
        except CompatibilityError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

        experiment = Experiment(
            name=config.name,
            config_hash=config_hash,
            config_json=json.dumps(config_dict),
            status=TaskStatus.IN_FLIGHT,
        )
        self.session.add(experiment)
        await self.session.commit()
        await self.session.refresh(experiment)

        await self._launch_graph(experiment, config_dict)
        return experiment

    async def list_experiments(self, limit: int, offset: int, status: str | None = None):
        return await self.repo.get_all(limit, offset, status)

    async def get_experiment(self, task_id: int):
        experiment = await self.repo.get_by_id(task_id)
        return experiment

    async def delete_experiment(self, task_id: int) -> bool:
        success = await self.repo.delete_experiment(task_id)
        if success:
            await self.session.commit()
            if task_id in _active_experiments:
                future = _active_experiments.pop(task_id)
                future.cancel()
        return success

    async def cancel_experiment(self, task_id: int) -> Experiment | None:
        experiment = await self.repo.get_by_id(task_id)
        if not experiment:
            return None
        if experiment.status in [TaskStatus.DONE, TaskStatus.ERROR, TaskStatus.CANCELLED]:
            raise HTTPException(
                status_code=400,
                detail=f"Completed, failed or cancelled experiments cannot be cancelled. Current status: {experiment.status}",
            )

        experiment.status = TaskStatus.CANCELLED
        self.session.add(experiment)
        await self.session.commit()
        await self.session.refresh(experiment)

        if task_id in _active_experiments:
            future = _active_experiments.pop(task_id)
            future.cancel()

        return experiment

    async def retry_experiment(self, task_id: int) -> Experiment | None:
        experiment = await self.repo.get_by_id(task_id)
        if not experiment:
            return None
        if experiment.status == TaskStatus.DONE:
            raise HTTPException(
                status_code=400,
                detail=f"Only failed, running or cancelled experiments can be retried. Current status: {experiment.status}",
            )

        experiment.status = TaskStatus.IN_FLIGHT
        experiment.error = None
        self.session.add(experiment)
        await self.session.commit()
        await self.session.refresh(experiment)

        config_dict = json.loads(experiment.config_json)
        await self._launch_graph(experiment, config_dict)
        return experiment
