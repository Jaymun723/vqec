import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlmodel import SQLModel
from dask.distributed import Client

from vqec.server.config import settings
from vqec.server.database import async_engine
from vqec.server.routers import registry, system, tasks
from vqec.server.models.db import Experiment, TaskStatus

logger = logging.getLogger(__name__)

dask_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global dask_client

    async with async_engine.begin() as conn:
        if settings.database_url.startswith("sqlite") and "memory" not in settings.database_url:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        await conn.run_sync(SQLModel.metadata.create_all)
        
        # After restart: "If an experiment is marked `IN_FLIGHT` but no corresponding Dask computation exists, 
        # it should transition to `ERROR` so it can later be retried."
        # We don't restore Dask state, so all IN_FLIGHT become ERROR
        await conn.execute(
            text("UPDATE experiment SET status = :new_status WHERE status = :old_status"),
            {"new_status": TaskStatus.ERROR.value, "old_status": TaskStatus.IN_FLIGHT.value}
        )

    from vqec.core.registry import scan_adapters

    scan_adapters(Path(__file__).parent.parent / "adapters")
    
    # Initialize Dask client
    dask_client = await Client(settings.dask_scheduler_address, asynchronous=True)

    yield

    if dask_client:
        await dask_client.close()
    await async_engine.dispose()


app = FastAPI(
    title="VQEC Server",
    version="0.1.0",
    description="Visualize Quantum Error Correction",
    lifespan=lifespan,
)

if settings.cors_origins:
    origins = [origin.strip() for origin in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(system.router)
app.include_router(registry.router, prefix="/registry", tags=["registry"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
