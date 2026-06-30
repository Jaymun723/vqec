import asyncio
import json
from pathlib import Path

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select as sqlmodel_select

from vqec.server.config import settings
from vqec.server.models.db import DataGenerationTask, DecodingTask, ExperimentTask


class ExportService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def build_parquet(self, experiment_id: int) -> str | None:
        stmt = sqlmodel_select(ExperimentTask).where(ExperimentTask.id == experiment_id)
        result = await self.session.execute(stmt)
        experiment = result.scalars().first()
        if not experiment:
            return None

        stmt = (
            sqlmodel_select(DecodingTask, DataGenerationTask)
            .join(DataGenerationTask, DecodingTask.data_generation_task_id == DataGenerationTask.id)
            .where(DecodingTask.experiment_id == experiment_id)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        if not rows:
            return None

        records = []
        for job, data_task in rows:
            decode_spec = json.loads(job.spec_json)
            data_spec = json.loads(data_task.spec_json)

            record = {
                "experiment_id": experiment.id,
                "experiment_name": experiment.name,
                "job_id": job.id,
                "status": job.status.value,
                "circuit_type": data_spec.get("circuit_type"),
                "noise_type": data_spec.get("noise_type"),
                "runner_type": data_spec.get("runner_type"),
                "decoder_type": decode_spec.get("decoder_type"),
            }

            for key, value in data_spec.get("circuit_params", {}).items():
                record[f"circuit_{key}"] = value
            for key, value in data_spec.get("noise_params", {}).items():
                record[f"noise_{key}"] = value
            for key, value in data_spec.get("runner_params", {}).items():
                record[f"runner_{key}"] = value
            for key, value in decode_spec.get("decoder_params", {}).items():
                record[f"decoder_{key}"] = value

            res = {
                "logical_error_rate": job.logical_error_rate,
                "n_errors": job.n_errors,
                "time_decoder_setup_s": job.time_decoder_setup_s,
                "time_decoder_decode_s": job.time_decoder_decode_s,
                "time_total_s": job.time_total_s,
                "shots": data_task.shots,
                "time_build_circuit_s": data_task.time_build_circuit_s,
                "time_apply_noise_s": data_task.time_apply_noise_s,
                "time_runner_run_s": data_task.time_runner_run_s,
                "time_pickle_write_s": data_task.time_pickle_write_s,
                "outcome_file_path": data_task.outcome_file_path,
            }
            if data_task.metadata_json:
                res.update(json.loads(data_task.metadata_json))
            if job.metadata_json:
                res.update(json.loads(job.metadata_json))

            record.update(res)
            records.append(record)

        if not records:
            return None

        exports_dir = Path(settings.storage_dir) / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        out_path = exports_dir / f"experiment_{experiment_id}.parquet"

        df = pd.DataFrame(records)
        await asyncio.to_thread(lambda: df.to_parquet(out_path, index=False))

        experiment.parquet_results_path = str(out_path)
        self.session.add(experiment)
        await self.session.commit()
        return str(out_path)
