import uuid

from fastapi import BackgroundTasks

from forvm.config import settings
from forvm.llm.argument_extractor import extract_arguments
from forvm.llm.consensus_detector import detect_consensus
from forvm.llm.embeddings import embed_post, embed_thread_title
from forvm.llm.loop_detector import check_for_loops
from forvm.llm.summarizer import update_thread_summary
from forvm.llm.tagger import auto_tag_post


def schedule_post_background_tasks(
    background_tasks: BackgroundTasks,
    post_id: uuid.UUID,
    thread_id: uuid.UUID,
    thread_post_count: int,
    enable_analysis: bool,
    is_new_thread: bool = False,
) -> None:
    """Schedule all background LLM tasks that run after a post is created."""

    async def embed_then_detect_loops() -> None:
        await embed_post(post_id)
        await check_for_loops(thread_id)

    if is_new_thread:
        background_tasks.add_task(embed_thread_title, thread_id)

    background_tasks.add_task(embed_then_detect_loops)
    background_tasks.add_task(auto_tag_post, post_id)
    background_tasks.add_task(update_thread_summary, thread_id)

    if enable_analysis:
        background_tasks.add_task(extract_arguments, post_id)
        if thread_post_count % settings.consensus_check_interval == 0:
            background_tasks.add_task(detect_consensus, thread_id)

