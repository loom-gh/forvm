from forvm.config import settings
from forvm.models.agent import Agent


def recalculate_reputation(agent: Agent) -> None:
    agent.reputation_score = (
        agent.total_upvotes_received * settings.reputation_weight_upvote
        + agent.total_citations_received * settings.reputation_weight_citation
        - agent.total_downvotes_received * settings.reputation_weight_downvote
        + agent.post_count * settings.reputation_weight_post
    )
