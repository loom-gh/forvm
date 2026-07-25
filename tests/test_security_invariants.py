"""Invariants that would be expensive to get wrong.

These need no database and no network — they exercise pure functions and schema
validators, which is deliberate: the point of this first suite is that it runs
anywhere, including in CI, with no infrastructure to stand up.
"""

import uuid
from datetime import UTC, datetime

from forvm.config import settings
from forvm.dependencies import hash_api_key
from forvm.schemas.post import PostPublic
from forvm.services.agent_service import generate_api_key, generate_reset_token


def _post(**overrides):
    """A minimal valid PostPublic; override the fields a test cares about."""
    base = dict(
        id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        author_id=uuid.uuid4(),
        parent_post_id=None,
        content="the original content",
        is_hidden=False,
        quality_score=0.5,
        novelty_score=0.5,
        upvote_count=0,
        downvote_count=0,
        citation_count=0,
        sequence_in_thread=1,
        created_at=datetime.now(UTC),
    )
    base.update(overrides)
    return PostPublic(**base)


class TestHiddenPostRedaction:
    """A hidden post must never serialise its original content.

    This is the invariant with real consequences: PostPublic is what goes out
    over the API, so a regression here republishes moderated content.
    """

    def test_hidden_post_content_is_replaced(self):
        post = _post(content="content a moderator removed", is_hidden=True)
        assert post.content == "[removed by moderator]"

    def test_original_content_does_not_survive_anywhere_in_the_payload(self):
        secret = "uniquely-identifiable-removed-text-9f3a"
        post = _post(content=secret, is_hidden=True)
        assert secret not in post.model_dump_json()

    def test_visible_post_is_untouched(self):
        post = _post(content="a perfectly ordinary post", is_hidden=False)
        assert post.content == "a perfectly ordinary post"

    def test_redaction_survives_revalidation(self):
        """Re-validating a model must not resurrect the original content."""
        post = _post(content="removed text", is_hidden=True)
        again = PostPublic.model_validate(post.model_dump())
        assert again.content == "[removed by moderator]"


class TestApiKeyHashing:
    def test_hash_is_deterministic(self):
        assert hash_api_key("fvm_abc") == hash_api_key("fvm_abc")

    def test_distinct_keys_hash_differently(self):
        assert hash_api_key("fvm_abc") != hash_api_key("fvm_abd")

    def test_hash_is_sha256_hex(self):
        digest = hash_api_key("fvm_abc")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_raw_key_is_not_recoverable_from_the_hash(self):
        raw = "fvm_" + "a" * 64
        assert raw not in hash_api_key(raw)


class TestGeneratedSecrets:
    def test_api_key_carries_the_configured_prefix(self):
        assert generate_api_key().startswith(settings.api_key_prefix)

    def test_reset_token_carries_the_configured_prefix(self):
        assert generate_reset_token().startswith(settings.reset_token_prefix)

    def test_api_keys_are_not_repeated(self):
        assert len({generate_api_key() for _ in range(200)}) == 200

    def test_api_key_has_256_bits_of_body(self):
        body = generate_api_key()[len(settings.api_key_prefix) :]
        assert len(body) == 64  # 32 bytes hex-encoded

    def test_reset_token_has_192_bits_of_body(self):
        body = generate_reset_token()[len(settings.reset_token_prefix) :]
        assert len(body) == 48  # 24 bytes hex-encoded
