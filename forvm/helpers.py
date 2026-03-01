import uuid
from collections.abc import Sequence
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def get_or_404(
    db: AsyncSession,
    model: type[T],
    id: uuid.UUID,
    detail: str = "Not found",
    *,
    options: list | None = None,
) -> T:
    query = select(model).where(model.id == id)  # type: ignore[attr-defined]
    if options:
        query = query.options(*options)
    result = await db.execute(query)
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=detail)
    return obj  # type: ignore[return-value]


async def paginate(
    db: AsyncSession,
    query: Select,
    page: int,
    per_page: int,
) -> tuple[Sequence[T], int]:
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page))
    items = result.scalars().all()

    return items, total
