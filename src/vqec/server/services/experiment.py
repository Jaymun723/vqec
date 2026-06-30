import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from vqec.core.experiment import Experiment, ExperimentConfig
from vqec.core.validator import CompatibilityError
from vqec.server.models.db import DataGenerationTask, DecodingTask, ExperimentTask, TaskStatus
from vqec.server.models.schemas import DecodingTaskRead, ExperimentTaskDetail, ExperimentTaskRead
from vqec.server.repositories.experiment import ExperimentRepository, PendingDecodingTask
from vqec.server.utils import compute_config_hash


class ExperimentService:
    def __init__(self, session: AsyncSession):
        self.repo = ExperimentRepository(session)
        self.session = session

    async def to_read(self, experiment: ExperimentTask) -> ExperimentTaskRead:
        completed, total = await self.repo.get_job_stats(experiment.id)
        return ExperimentTaskRead(
            id=experiment.id,
            name=experiment.name,
            config_hash=experiment.config_hash,
            status=experiment.status,
            completed_jobs=completed,
            total_jobs=total,
            error_message=experiment.error_message,
            created_at=experiment.created_at,
            updated_at=experiment.updated_at,
        )

    async def to_detail(self, experiment: ExperimentTask, jobs: list[DecodingTask]) -> ExperimentTaskDetail:
        summary = await self.to_read(experiment)
        job_reads = [
            DecodingTaskRead(
                id=job.id,
                status=job.status,
                logical_error_rate=job.logical_error_rate,
                n_errors=job.n_errors,
                time_total_s=job.time_total_s,
                error_message=job.error_message,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            for job in jobs
        ]
        return ExperimentTaskDetail(
            **summary.model_dump(),
            config=json.loads(experiment.config_json),
            jobs=job_reads,
        )

    async def submit_experiment(self, config_dict: dict) -> ExperimentTask:
        config_hash = compute_config_hash(config_dict)

        existing = await self.repo.get_by_hash(config_hash)
        if existing:
            return existing

        try:
            config = ExperimentConfig.model_validate(config_dict)
            experiment_model = Experiment(config)
            experiment_model.validate_compatibility()
        except CompatibilityError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

        jobs = experiment_model.expand_jobs()

        experiment = ExperimentTask(
            name=config.name,
            config_hash=config_hash,
            config_json=json.dumps(config_dict),
            status=TaskStatus.PENDING,
        )

        data_tasks: list[DataGenerationTask] = []
        decoding_tasks: list[PendingDecodingTask] = []
        seen_data_hashes: set[str] = set()

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

            if data_hash not in seen_data_hashes:
                seen_data_hashes.add(data_hash)
                data_tasks.append(
                    DataGenerationTask(
                        config_hash=data_hash,
                        spec_json=json.dumps(data_spec_dict),
                    )
                )

            decode_spec_dict = {
                "decoder_type": job.decode_spec.decoder_type,
                "decoder_params": job.decode_spec.decoder_params,
            }
            decoder_type = job.decode_spec.decoder_type.lower()
            requires_gpu = "gpu" in decoder_type or "ml" in decoder_type

            decoding_tasks.append(
                PendingDecodingTask(
                    requires_gpu=requires_gpu,
                    spec_json=json.dumps(decode_spec_dict),
                    data_config_hash=data_hash,
                )
            )

        created = await self.repo.create_experiment_and_jobs(experiment, data_tasks, decoding_tasks)
        await self.session.commit()
        return created

    async def list_experiments(self, limit: int, offset: int, status: str | None = None):
        return await self.repo.get_all(limit, offset, status)

    async def get_experiment(self, task_id: int):
        experiment = await self.repo.get_by_id(task_id)
        if not experiment:
            return None
        jobs = await self.repo.get_jobs(task_id)
        return experiment, jobs

    async def delete_experiment(self, task_id: int) -> bool:
        success = await self.repo.delete_experiment(task_id)
        if success:
            await self.session.commit()
        return success

    async def cancel_experiment(self, task_id: int) -> ExperimentTask | None:
        from sqlalchemy import update

        experiment = await self.repo.get_by_id(task_id)
        if not experiment:
            return None
        if experiment.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            raise HTTPException(
                status_code=400,
                detail=f"Completed, failed or cancelled experiments cannot be cancelled. Current status: {experiment.status}",
            )

        experiment.status = TaskStatus.CANCELLED
        self.session.add(experiment)

        stmt = (
            update(DecodingTask)
            .where(
                DecodingTask.experiment_id == task_id,
                DecodingTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
            )
            .values(status=TaskStatus.CANCELLED)
        )
        await self.session.execute(stmt)
        await self.session.commit()
        await self.session.refresh(experiment)
        return experiment

    async def retry_experiment(self, task_id: int) -> ExperimentTask | None:
        from sqlalchemy import update

        experiment = await self.repo.get_by_id(task_id)
        if not experiment:
            return None
        if experiment.status == TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Only failed, running or cancelled experiments can be retried. Current status: {experiment.status}",
            )

        experiment.status = TaskStatus.PENDING
        experiment.error_message = None
        self.session.add(experiment)

        stmt = (
            update(DecodingTask)
            .where(
                DecodingTask.experiment_id == task_id,
                DecodingTask.status.in_([TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.RUNNING]),
            )
            .values(status=TaskStatus.PENDING, error_message=None)
        )
        await self.session.execute(stmt)

        jobs = await self.repo.get_jobs(task_id)
        data_task_ids = list({job.data_generation_task_id for job in jobs})

        if data_task_ids:
            stmt_data = (
                update(DataGenerationTask)
                .where(
                    DataGenerationTask.id.in_(data_task_ids),
                    DataGenerationTask.status.in_([TaskStatus.FAILED, TaskStatus.CANCELLED]),
                )
                .values(status=TaskStatus.PENDING, error_message=None)
            )
            await self.session.execute(stmt_data)

        await self.session.commit()
        await self.session.refresh(experiment)
        return experiment
