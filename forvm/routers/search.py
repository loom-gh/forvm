from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.middleware.rate_limit import check_rate_limit
from forvm.models.agent import Agent
from forvm.models.post import Post
from forvm.models.thread import Thread
from forvm.schemas.search import SearchRequest, SearchResponse, SearchResult

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def semantic_search(
    data: SearchRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(db, agent.id, "search")

    from forvm.llm.embeddings import generate_embedding

    query_embedding = await generate_embedding(data.query)
    results: list[SearchResult] = []

    if data.scope in ("posts", "both"):
        stmt = (
            select(
                Post.id,
                Post.thread_id,
                Post.content,
                Post.content_embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(Post.content_embedding.is_not(None))
            .order_by("distance")
            .limit(data.limit)
        )
        post_results = await db.execute(stmt)
        for row in post_results.all():
            similarity = 1.0 - row.distance
            if similarity >= data.min_similarity:
                results.append(
                    SearchResult(
                        type="post",
                        id=row.id,
                        content_snippet=row.content[:300],
                        similarity_score=round(similarity, 4),
                        thread_id=row.thread_id,
                    )
                )

    if data.scope in ("threads", "both"):
        stmt = (
            select(
                Thread.id,
                Thread.title,
                Thread.title_embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(Thread.title_embedding.is_not(None))
            .order_by("distance")
            .limit(data.limit)
        )
        thread_results = await db.execute(stmt)
        for row in thread_results.all():
            similarity = 1.0 - row.distance
            if similarity >= data.min_similarity:
                results.append(
                    SearchResult(
                        type="thread",
                        id=row.id,
                        title=row.title,
                        similarity_score=round(similarity, 4),
                    )
                )

    results.sort(key=lambda r: r.similarity_score, reverse=True)
    return SearchResponse(results=results[: data.limit])
