from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select as sqlmodel_select
from typing import List

from vqec.server.models.db import ExperimentTask, DataGenerationTask, DecodingTask, TaskStatus


@dataclass
class PendingDecodingTask:
    requires_gpu: bool
    spec_json: str
    data_config_hash: str


class ExperimentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_hash(self, config_hash: str) -> ExperimentTask | None:
        stmt = sqlmodel_select(ExperimentTask).where(ExperimentTask.config_hash == config_hash)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id(self, task_id: int) -> ExperimentTask | None:
        stmt = sqlmodel_select(ExperimentTask).where(ExperimentTask.id == task_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all(
        self, limit: int = 100, offset: int = 0, status: str | None = None
    ) -> List[ExperimentTask]:
        stmt = (
            sqlmodel_select(ExperimentTask)
            .order_by(ExperimentTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(ExperimentTask.status == status)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_jobs(self, experiment_id: int) -> List[DecodingTask]:
        stmt = sqlmodel_select(DecodingTask).where(DecodingTask.experiment_id == experiment_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_job_stats(self, experiment_id: int) -> tuple[int, int]:
        jobs = await self.get_jobs(experiment_id)
        completed = sum(1 for job in jobs if job.status == TaskStatus.COMPLETED)
        return completed, len(jobs)

    async def create_experiment_and_jobs(
        self,
        experiment: ExperimentTask,
        data_tasks: List[DataGenerationTask],
        decoding_tasks: List[PendingDecodingTask],
    ) -> ExperimentTask:
        self.session.add(experiment)
        await self.session.flush()

        data_hashes = [task.config_hash for task in data_tasks]
        stmt = sqlmodel_select(DataGenerationTask).where(DataGenerationTask.config_hash.in_(data_hashes))
        result = await self.session.execute(stmt)
        existing_data = {task.config_hash: task for task in result.scalars().all()}

        new_data_tasks = [task for task in data_tasks if task.config_hash not in existing_data]
        if new_data_tasks:
            self.session.add_all(new_data_tasks)
            await self.session.flush()
            for task in new_data_tasks:
                existing_data[task.config_hash] = task

        for pending in decoding_tasks:
            decoding_task = DecodingTask(
                experiment_id=experiment.id,
                data_generation_task_id=existing_data[pending.data_config_hash].id,
                requires_gpu=pending.requires_gpu,
                spec_json=pending.spec_json,
            )
            self.session.add(decoding_task)

        await self.session.flush()
        return experiment

    async def delete_experiment(self, task_id: int) -> bool:
        exp = await self.get_by_id(task_id)
        if not exp:
            return False
        await self.session.delete(exp)
        await self.session.flush()
        return True
