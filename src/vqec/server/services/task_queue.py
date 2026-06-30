import json
from datetime import timedelta

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select as sqlmodel_select

from vqec.server.config import settings
from vqec.server.models.db import DataGenerationTask, DecodingTask, ExperimentTask, TaskStatus
from vqec.server.models.schemas import DecodingMetrics, WorkerTaskSpec
from vqec.server.utils import utc_now


class TaskQueueService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def poll_tasks(self, batch_size: int, has_gpu: bool) -> list[WorkerTaskSpec]:
        tasks_assigned: list[WorkerTaskSpec] = []
        now = utc_now()
        lease_duration = timedelta(seconds=settings.task_lease_seconds)
        affected_experiment_ids: set[int] = set()

        await self.session.execute(text("BEGIN IMMEDIATE;"))

        try:
            stmt = (
                sqlmodel_select(DataGenerationTask)
                .where(DataGenerationTask.status == TaskStatus.PENDING)
                .limit(batch_size)
            )
            result = await self.session.execute(stmt)
            data_tasks = result.scalars().all()

            for data_task in data_tasks:
                data_task.status = TaskStatus.RUNNING
                data_task.leased_until = now + lease_duration
                self.session.add(data_task)

                exp_stmt = sqlmodel_select(DecodingTask.experiment_id).where(
                    DecodingTask.data_generation_task_id == data_task.id
                )
                exp_result = await self.session.execute(exp_stmt)
                affected_experiment_ids.update(exp_result.scalars().all())

                tasks_assigned.append(
                    WorkerTaskSpec(
                        type="data_generation",
                        id=data_task.id,
                        spec=json.loads(data_task.spec_json),
                    )
                )

            remaining_slots = batch_size - len(tasks_assigned)

            if remaining_slots > 0:
                stmt = (
                    sqlmodel_select(DecodingTask, DataGenerationTask.spec_json)
                    .join(DataGenerationTask, DecodingTask.data_generation_task_id == DataGenerationTask.id)
                    .join(ExperimentTask, DecodingTask.experiment_id == ExperimentTask.id)
                    .where(
                        DecodingTask.status == TaskStatus.PENDING,
                        DataGenerationTask.status == TaskStatus.COMPLETED,
                        ExperimentTask.status != TaskStatus.CANCELLED,
                    )
                )
                if not has_gpu:
                    stmt = stmt.where(DecodingTask.requires_gpu == False)

                stmt = stmt.limit(remaining_slots)
                result = await self.session.execute(stmt)

                for decoding_task, data_spec_json in result.all():
                    decoding_task.status = TaskStatus.RUNNING
                    decoding_task.leased_until = now + lease_duration
                    self.session.add(decoding_task)
                    affected_experiment_ids.add(decoding_task.experiment_id)

                    tasks_assigned.append(
                        WorkerTaskSpec(
                            type="decoding",
                            id=decoding_task.id,
                            data_id=decoding_task.data_generation_task_id,
                            spec=json.loads(decoding_task.spec_json),
                            data_spec=json.loads(data_spec_json),
                        )
                    )

            if affected_experiment_ids:
                await self.session.execute(
                    update(ExperimentTask)
                    .where(
                        ExperimentTask.id.in_(affected_experiment_ids),
                        ExperimentTask.status == TaskStatus.PENDING,
                    )
                    .values(status=TaskStatus.RUNNING)
                )

            await self.session.commit()
            return tasks_assigned
        except Exception:
            await self.session.rollback()
            raise

    async def heartbeat(self, task_ids: list[int]) -> bool:
        if not task_ids:
            return False

        now = utc_now()
        lease_until = now + timedelta(seconds=settings.task_lease_seconds)

        result_data = await self.session.execute(
            update(DataGenerationTask)
            .where(
                DataGenerationTask.id.in_(task_ids),
                DataGenerationTask.status == TaskStatus.RUNNING,
            )
            .values(leased_until=lease_until)
        )
        result_decode = await self.session.execute(
            update(DecodingTask)
            .where(
                DecodingTask.id.in_(task_ids),
                DecodingTask.status == TaskStatus.RUNNING,
            )
            .values(leased_until=lease_until)
        )

        updated = (result_data.rowcount or 0) + (result_decode.rowcount or 0)
        await self.session.commit()
        return updated > 0

    async def complete_task(
        self,
        task_type: str,
        task_id: int,
        status: TaskStatus,
        metrics: dict | None = None,
        error_message: str | None = None,
    ) -> bool:
        if task_type == "data_generation":
            stmt = sqlmodel_select(DataGenerationTask).where(DataGenerationTask.id == task_id)
            result = await self.session.execute(stmt)
            data_task = result.scalars().first()
            if not data_task:
                return False

            if data_task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                return True

            data_task.status = status
            data_task.error_message = error_message
            self.session.add(data_task)

            if status == TaskStatus.FAILED:
                exp_stmt = sqlmodel_select(DecodingTask.experiment_id).where(
                    DecodingTask.data_generation_task_id == data_task.id
                )
                exp_result = await self.session.execute(exp_stmt)
                experiment_ids = list(set(exp_result.scalars().all()))

                await self.session.execute(
                    update(DecodingTask)
                    .where(
                        DecodingTask.data_generation_task_id == data_task.id,
                        DecodingTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                    )
                    .values(status=TaskStatus.FAILED, error_message=error_message)
                )
                await self.session.flush()

                for experiment_id in experiment_ids:
                    await self._rollup_experiment(experiment_id)

        elif task_type == "decoding":
            stmt = sqlmodel_select(DecodingTask).where(DecodingTask.id == task_id)
            result = await self.session.execute(stmt)
            decoding_task = result.scalars().first()
            if not decoding_task:
                return False

            if decoding_task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                return True

            decoding_task.status = status
            decoding_task.error_message = error_message
            if metrics:
                decoding_task.logical_error_rate = metrics.get("logical_error_rate")
                decoding_task.n_errors = metrics.get("n_errors")
                decoding_task.time_decoder_setup_s = metrics.get("time_decoder_setup_s")
                decoding_task.time_decoder_decode_s = metrics.get("time_decoder_decode_s")
                decoding_task.time_total_s = metrics.get("time_total_s")
                
                metadata = {k: v for k, v in metrics.items() if k not in [
                    "logical_error_rate", "n_errors", "time_decoder_setup_s", 
                    "time_decoder_decode_s", "time_total_s"
                ]}
                if metadata:
                    decoding_task.metadata_json = json.dumps(metadata)
            self.session.add(decoding_task)
            await self.session.flush()
            await self._rollup_experiment(decoding_task.experiment_id)
        else:
            return False

        await self.session.commit()
        return True

    async def _rollup_experiment(self, experiment_id: int) -> None:
        experiment = await self.session.get(ExperimentTask, experiment_id)
        if not experiment or experiment.status == TaskStatus.CANCELLED:
            return

        stmt = sqlmodel_select(DecodingTask.status).where(DecodingTask.experiment_id == experiment_id)
        result = await self.session.execute(stmt)
        statuses = list(result.scalars().all())
        if not statuses:
            return

        if all(status == TaskStatus.COMPLETED for status in statuses):
            new_status = TaskStatus.COMPLETED
        elif any(status == TaskStatus.FAILED for status in statuses):
            new_status = TaskStatus.FAILED
        elif any(status in (TaskStatus.RUNNING, TaskStatus.PENDING) for status in statuses):
            new_status = TaskStatus.RUNNING
        else:
            new_status = TaskStatus.PENDING

        await self.session.execute(
            update(ExperimentTask)
            .where(ExperimentTask.id == experiment_id)
            .values(status=new_status)
        )

    async def upload_outcome(self, task_id: int, file_path: str, shots: int, metrics: dict) -> bool:
        stmt = sqlmodel_select(DataGenerationTask).where(DataGenerationTask.id == task_id)
        result = await self.session.execute(stmt)
        data_task = result.scalars().first()
        if not data_task:
            return False

        if data_task.status == TaskStatus.COMPLETED:
            return True

        data_task.outcome_file_path = file_path
        data_task.shots = shots
        data_task.time_build_circuit_s = metrics.get("time_build_circuit_s")
        data_task.time_apply_noise_s = metrics.get("time_apply_noise_s")
        data_task.time_runner_run_s = metrics.get("time_runner_run_s")
        data_task.time_pickle_write_s = metrics.get("time_pickle_write_s")
        
        metadata = {k: v for k, v in metrics.items() if k not in [
            "shots", "time_build_circuit_s", "time_apply_noise_s", 
            "time_runner_run_s", "time_pickle_write_s"
        ]}
        if metadata:
            data_task.metadata_json = json.dumps(metadata)
            
        data_task.status = TaskStatus.COMPLETED
        self.session.add(data_task)
        await self.session.commit()
        return True

    async def get_outcome_path(self, data_id: int) -> str | None:
        stmt = sqlmodel_select(DataGenerationTask).where(DataGenerationTask.id == data_id)
        result = await self.session.execute(stmt)
        data_task = result.scalars().first()
        return data_task.outcome_file_path if data_task else None
