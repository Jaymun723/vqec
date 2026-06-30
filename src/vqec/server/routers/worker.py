import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vqec.server.config import settings
from vqec.server.database import get_session
from vqec.server.models.schemas import (
    WorkerCompleteRequest,
    WorkerHeartbeatRequest,
    WorkerPollRequest,
    WorkerPollResponse,
    WorkerStatusResponse,
)
from vqec.server.services.task_queue import TaskQueueService

router = APIRouter()


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@router.post("/poll", response_model=WorkerPollResponse)
async def poll_tasks(request: WorkerPollRequest, session: AsyncSession = Depends(get_session)):
    service = TaskQueueService(session)
    tasks = await service.poll_tasks(request.batch_size, request.has_gpu)
    return WorkerPollResponse(tasks=tasks)


@router.post("/heartbeat", response_model=WorkerStatusResponse)
async def heartbeat(request: WorkerHeartbeatRequest, session: AsyncSession = Depends(get_session)):
    service = TaskQueueService(session)
    success = await service.heartbeat(request.task_ids)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or not running")
    return WorkerStatusResponse()


@router.post("/upload/{task_id}", response_model=WorkerStatusResponse)
async def upload_outcome(
    task_id: int,
    file: UploadFile = File(...),
    shots: int = Form(...),
    metrics_json: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Upload exceeds maximum allowed size")

    storage_dir = Path(settings.storage_dir) / "outcomes"
    file_path = storage_dir / f"{task_id}.pkl.gz"
    await asyncio.to_thread(_write_bytes, file_path, content)

    metrics = json.loads(metrics_json)
    service = TaskQueueService(session)
    success = await service.upload_outcome(task_id, str(file_path), shots, metrics)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")

    return WorkerStatusResponse()


@router.get("/download/{data_id}")
async def download_outcome(data_id: int, session: AsyncSession = Depends(get_session)):
    service = TaskQueueService(session)
    path_str = await service.get_outcome_path(data_id)
    if not path_str:
        raise HTTPException(status_code=404, detail="Data generation outcome not found")

    path = Path(path_str)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File absent on disk")

    return FileResponse(path, media_type="application/gzip")


@router.post("/complete", response_model=WorkerStatusResponse)
async def complete_task(request: WorkerCompleteRequest, session: AsyncSession = Depends(get_session)):
    service = TaskQueueService(session)
    success = await service.complete_task(
        task_type=request.type,
        task_id=request.id,
        status=request.status,
        metrics=request.metrics,
        error_message=request.error_message,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return WorkerStatusResponse()
