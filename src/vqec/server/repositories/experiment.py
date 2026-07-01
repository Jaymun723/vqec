from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select as sqlmodel_select
from typing import List

from vqec.server.models.db import Experiment, DataCache, DecodeCache, TaskStatus


class ExperimentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_hash(self, config_hash: str) -> Experiment | None:
        stmt = sqlmodel_select(Experiment).where(Experiment.config_hash == config_hash)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id(self, task_id: int) -> Experiment | None:
        stmt = sqlmodel_select(Experiment).where(Experiment.id == task_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all(
        self, limit: int = 100, offset: int = 0, status: str | None = None
    ) -> List[Experiment]:
        stmt = (
            sqlmodel_select(Experiment)
            .order_by(Experiment.submitted_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(Experiment.status == status)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_experiment(self, task_id: int) -> bool:
        exp = await self.get_by_id(task_id)
        if not exp:
            return False
        await self.session.delete(exp)
        await self.session.flush()
        return True
