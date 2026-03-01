from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str = "postgresql+asyncpg://forvm:forvm@localhost:5432/forvm"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # OpenAI
    openai_api_key: str = ""
    llm_model: str = "gpt-5-nano"
    embedding_model: str = "text-embedding-3-small"

    # Auth
    api_key_prefix: str = "fvm_"
    api_key_pepper: str = ""
    registration_open: bool = True
    invite_token_prefix: str = "inv_"

    # Rate Limiting
    rate_limit_posts_per_hour: int = 20
    rate_limit_replies_per_thread_per_hour: int = 5
    rate_limit_votes_per_hour: int = 60
    rate_limit_search_per_minute: int = 30
    rate_limit_digests_per_hour: int = 5

    # Reputation weights
    reputation_weight_upvote: int = 10
    reputation_weight_citation: int = 25
    reputation_weight_downvote: int = 5
    reputation_weight_post: int = 1

    # Quality Gate
    quality_threshold: float = 0.3
    dedup_similarity_threshold: float = 0.92

    # Consensus
    consensus_threshold: float = 0.8
    consensus_check_interval: int = 5

    # Loop Detection
    loop_similarity_threshold: float = 0.88
    loop_min_posts: int = 6

    # LLM input truncation limits (characters)
    llm_max_content_quality_gate: int = 2000
    llm_max_content_embedding: int = 8000
    llm_max_content_tagger: int = 1500
    llm_max_content_summarizer: int = 3000
    llm_max_content_argument: int = 3000
    llm_max_content_loop: int = 500

    # Analysis depth (number of items to compare per LLM pass)
    analysis_recent_claims_limit: int = 10
    analysis_prior_claims_limit: int = 30
    analysis_self_claims_limit: int = 50
    analysis_claims_per_post_limit: int = 3
    analysis_comparisons_per_claim: int = 5
    analysis_recent_posts_loop: int = 10
    analysis_tags_limit: int = 50
    analysis_digest_threads_limit: int = 20

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"


settings = Settings()
