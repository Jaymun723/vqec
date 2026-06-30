import json
import pytest
from unittest.mock import AsyncMock

from vqec.server.models.db import DataGenerationTask, DecodingTask, ExperimentTask, TaskStatus
from vqec.server.models.schemas import DecodingMetrics
from vqec.server.services.task_queue import TaskQueueService

pytestmark = pytest.mark.asyncio


async def test_heartbeat_empty_task_ids(session):
    service = TaskQueueService(session)
    assert await service.heartbeat([]) is False


async def test_complete_task_invalid_type(session):
    service = TaskQueueService(session)
    assert await service.complete_task("unknown", 1, TaskStatus.FAILED) is False


async def test_complete_task_idempotent_decoding(session):
    experiment = ExperimentTask(
        name="exp",
        config_hash="hash1",
        config_json="{}",
        status=TaskStatus.PENDING,
    )
    data_task = DataGenerationTask(config_hash="dhash", spec_json="{}", status=TaskStatus.COMPLETED)
    session.add_all([experiment, data_task])
    await session.flush()

    decoding = DecodingTask(
        experiment_id=experiment.id,
        data_generation_task_id=data_task.id,
        requires_gpu=False,
        spec_json="{}",
        status=TaskStatus.COMPLETED,
        logical_error_rate=0.1,
        n_errors=1,
    )
    session.add(decoding)
    await session.commit()

    service = TaskQueueService(session)
    assert await service.complete_task("decoding", decoding.id, TaskStatus.COMPLETED) is True


async def test_upload_outcome_idempotent(session):
    data_task = DataGenerationTask(
        config_hash="dhash2",
        spec_json="{}",
        status=TaskStatus.COMPLETED,
        outcome_file_path="/tmp/x.pkl.gz",
    )
    session.add(data_task)
    await session.commit()

    service = TaskQueueService(session)
    assert await service.upload_outcome(data_task.id, "/tmp/y.pkl.gz", 10, {}) is True


async def test_rollup_skips_cancelled_experiment(session):
    experiment = ExperimentTask(
        name="cancelled",
        config_hash="hash2",
        config_json="{}",
        status=TaskStatus.CANCELLED,
    )
    data_task = DataGenerationTask(config_hash="dhash3", spec_json="{}", status=TaskStatus.COMPLETED)
    session.add_all([experiment, data_task])
    await session.flush()

    decoding = DecodingTask(
        experiment_id=experiment.id,
        data_generation_task_id=data_task.id,
        requires_gpu=False,
        spec_json="{}",
        status=TaskStatus.PENDING,
    )
    session.add(decoding)
    await session.commit()

    service = TaskQueueService(session)
    await service._rollup_experiment(experiment.id)
    await session.refresh(experiment)
    assert experiment.status == TaskStatus.CANCELLED


async def test_rollup_pending_when_all_decoding_cancelled(session):
    experiment = ExperimentTask(
        name="mixed",
        config_hash="hash3",
        config_json="{}",
        status=TaskStatus.RUNNING,
    )
    data_task = DataGenerationTask(config_hash="dhash4", spec_json="{}", status=TaskStatus.COMPLETED)
    session.add_all([experiment, data_task])
    await session.flush()

    decoding = DecodingTask(
        experiment_id=experiment.id,
        data_generation_task_id=data_task.id,
        requires_gpu=False,
        spec_json="{}",
        status=TaskStatus.CANCELLED,
    )
    session.add(decoding)
    await session.commit()

    service = TaskQueueService(session)
    await service._rollup_experiment(experiment.id)
    await session.refresh(experiment)
    assert experiment.status == TaskStatus.PENDING


async def test_poll_rollback_on_commit_failure(session, monkeypatch):
    service = TaskQueueService(session)
    monkeypatch.setattr(session, "commit", AsyncMock(side_effect=RuntimeError("commit failed")))

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.poll_tasks(batch_size=1, has_gpu=False)


async def test_get_outcome_path_missing(session):
    service = TaskQueueService(session)
    assert await service.get_outcome_path(99999) is None


async def test_rollup_no_decoding_tasks(session):
    experiment = ExperimentTask(
        name="no-jobs",
        config_hash="hash-no-jobs",
        config_json="{}",
        status=TaskStatus.RUNNING,
    )
    session.add(experiment)
    await session.commit()

    service = TaskQueueService(session)
    await service._rollup_experiment(experiment.id)
    await session.refresh(experiment)
    assert experiment.status == TaskStatus.RUNNING


async def test_complete_data_generation_idempotent(session):
    data_task = DataGenerationTask(
        config_hash="dhash-idem",
        spec_json="{}",
        status=TaskStatus.COMPLETED,
    )
    session.add(data_task)
    await session.commit()

    service = TaskQueueService(session)
    assert await service.complete_task("data_generation", data_task.id, TaskStatus.FAILED) is True


async def test_rollup_running_with_pending_job(session):
    experiment = ExperimentTask(
        name="running",
        config_hash="hash-running",
        config_json="{}",
        status=TaskStatus.PENDING,
    )
    data_task = DataGenerationTask(config_hash="dhash-run", spec_json="{}", status=TaskStatus.COMPLETED)
    session.add_all([experiment, data_task])
    await session.flush()

    completed = DecodingTask(
        experiment_id=experiment.id,
        data_generation_task_id=data_task.id,
        requires_gpu=False,
        spec_json="{}",
        status=TaskStatus.COMPLETED,
    )
    pending = DecodingTask(
        experiment_id=experiment.id,
        data_generation_task_id=data_task.id,
        requires_gpu=False,
        spec_json="{}",
        status=TaskStatus.PENDING,
    )
    session.add_all([completed, pending])
    await session.commit()

    service = TaskQueueService(session)
    await service._rollup_experiment(experiment.id)
    await session.refresh(experiment)
    assert experiment.status == TaskStatus.RUNNING


async def test_complete_decoding_with_metrics(session):
    experiment = ExperimentTask(
        name="metrics",
        config_hash="hash4",
        config_json="{}",
        status=TaskStatus.RUNNING,
    )
    data_task = DataGenerationTask(config_hash="dhash5", spec_json="{}", status=TaskStatus.COMPLETED)
    session.add_all([experiment, data_task])
    await session.flush()

    decoding = DecodingTask(
        experiment_id=experiment.id,
        data_generation_task_id=data_task.id,
        requires_gpu=False,
        spec_json=json.dumps({"decoder_type": "x", "decoder_params": {}}),
        status=TaskStatus.RUNNING,
    )
    session.add(decoding)
    await session.commit()

    service = TaskQueueService(session)
    metrics = {
        "logical_error_rate": 0.05,
        "n_errors": 5,
        "time_decoder_setup_s": 0.1,
        "time_decoder_decode_s": 0.2,
        "time_total_s": 0.3,
    }
    assert await service.complete_task("decoding", decoding.id, TaskStatus.COMPLETED, metrics=metrics)
    await session.refresh(experiment)
    assert experiment.status == TaskStatus.COMPLETED
