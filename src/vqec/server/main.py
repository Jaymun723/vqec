import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlmodel import SQLModel

from vqec.server.config import settings
from vqec.server.database import async_engine
from vqec.server.routers import registry, system, tasks, worker

logger = logging.getLogger(__name__)


async def _export_loop(stop: asyncio.Event) -> None:
    from vqec.server.workers.export_worker import process_exports

    while not stop.is_set():
        try:
            if settings.export_worker:
                await process_exports()
        except Exception as exc:
            logger.error("Export loop error: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=5)
        except TimeoutError:
            continue


async def _lease_loop(stop: asyncio.Event) -> None:
    from vqec.server.workers.update_worker import process_expired_leases

    while not stop.is_set():
        try:
            await process_expired_leases()
        except Exception as exc:
            logger.error("Lease loop error: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_engine.begin() as conn:
        if settings.database_url.startswith("sqlite") and "memory" not in settings.database_url:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        await conn.run_sync(SQLModel.metadata.create_all)

    from vqec.core.registry import scan_adapters

    scan_adapters(Path(__file__).parent.parent / "adapters")

    stop = asyncio.Event()
    export_task = asyncio.create_task(_export_loop(stop))
    lease_task = asyncio.create_task(_lease_loop(stop))

    yield

    stop.set()
    export_task.cancel()
    lease_task.cancel()
    await asyncio.gather(export_task, lease_task, return_exceptions=True)
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
app.include_router(worker.router, prefix="/worker", tags=["worker"])
