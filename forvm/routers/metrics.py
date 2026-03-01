from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_db
from forvm.schemas.metrics import PlatformMetrics
from forvm.services.metrics_service import compute_metrics

router = APIRouter()


@router.get("/metrics", response_model=PlatformMetrics)
async def get_metrics(db: AsyncSession = Depends(get_db)):
    return await compute_metrics(db)
