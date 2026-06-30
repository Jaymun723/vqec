from fastapi import APIRouter
from vqec.server.models.schemas import SystemInfo

router = APIRouter()

@router.get("/", response_model=SystemInfo)
async def get_system_info():
    return SystemInfo(
        name="VQEC Server",
        version="0.1.0",
        status="online",
        documentation="/docs",
        registry="/registry"
    )
