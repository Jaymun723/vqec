from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from vqec.server.database import get_session
from vqec.server.models.schemas import ExperimentRead, ExperimentDetail, ExperimentDeletedRead
from vqec.server.services.experiment import ExperimentService

router = APIRouter()


@router.post("/experiment", response_model=ExperimentRead)
async def submit_experiment(config: dict, session: AsyncSession = Depends(get_session)):
    service = ExperimentService(session)
    experiment = await service.submit_experiment(config)
    return await service.to_read(experiment)


@router.get("/experiment", response_model=list[ExperimentRead])
async def list_experiments(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    service = ExperimentService(session)
    experiments = await service.list_experiments(limit, offset, status)
    return [await service.to_read(experiment) for experiment in experiments]


@router.get("/experiment/{task_id}", response_model=ExperimentDetail)
async def get_experiment(task_id: int, session: AsyncSession = Depends(get_session)):
    service = ExperimentService(session)
    experiment = await service.get_experiment(task_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return await service.to_detail(experiment)


@router.get("/experiment/{task_id}/download")
async def download_experiment_results(task_id: int, session: AsyncSession = Depends(get_session)):
    service = ExperimentService(session)
    experiment = await service.get_experiment(task_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    if experiment.status != "DONE":
        raise HTTPException(status_code=400, detail="Experiment is not DONE yet")

    if not experiment.result_path or not Path(experiment.result_path).exists():
        return JSONResponse(status_code=202, content={"detail": "Parquet export still in progress or not found"})

    return FileResponse(experiment.result_path, media_type="application/octet-stream")


@router.post("/experiment/{task_id}/cancel", response_model=ExperimentRead)
async def cancel_experiment(task_id: int, session: AsyncSession = Depends(get_session)):
    service = ExperimentService(session)
    experiment = await service.cancel_experiment(task_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return await service.to_read(experiment)


@router.post("/experiment/{task_id}/retry", response_model=ExperimentRead)
async def retry_experiment(task_id: int, session: AsyncSession = Depends(get_session)):
    service = ExperimentService(session)
    experiment = await service.retry_experiment(task_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return await service.to_read(experiment)


@router.delete("/experiment/{task_id}", response_model=ExperimentDeletedRead)
async def delete_experiment(task_id: int, session: AsyncSession = Depends(get_session)):
    service = ExperimentService(session)
    experiment = await service.get_experiment(task_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    success = await service.delete_experiment(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Could not delete experiment")

    return ExperimentDeletedRead(
        id=experiment.id,
        name=experiment.name,
        config_hash=experiment.config_hash,
    )
