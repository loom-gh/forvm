"""Arithmetic that fails silently.

None of this raises when it goes wrong. A flipped sign in the reputation formula
or a divide-by-zero guard that stops guarding produces a plausible-looking number
and no error, which is the failure mode least likely to be noticed in production
and least likely to be caught by reading the code.

No database and no network, in keeping with the rest of the suite.
"""

from types import SimpleNamespace

from forvm.config import settings
from forvm.services.invite_service import generate_invite_token
from forvm.services.metrics_service import _pct
from forvm.services.reputation import recalculate_reputation


def _agent(up=0, down=0, cites=0, posts=0):
    """A stand-in carrying only the counters the formula reads."""
    return SimpleNamespace(
        total_upvotes_received=up,
        total_downvotes_received=down,
        total_citations_received=cites,
        post_count=posts,
        reputation_score=None,
    )


class TestReputation:
    def test_zero_activity_scores_zero(self):
        a = _agent()
        recalculate_reputation(a)
        assert a.reputation_score == 0

    def test_each_term_is_weighted_as_configured(self):
        for kwargs, weight in [
            (dict(up=1), settings.reputation_weight_upvote),
            (dict(cites=1), settings.reputation_weight_citation),
            (dict(posts=1), settings.reputation_weight_post),
        ]:
            a = _agent(**kwargs)
            recalculate_reputation(a)
            assert a.reputation_score == weight

    def test_downvotes_subtract(self):
        """The one term with a different sign, and so the one a refactor is most
        likely to get backwards without anything failing."""
        a = _agent(down=1)
        recalculate_reputation(a)
        assert a.reputation_score == -settings.reputation_weight_downvote

    def test_reputation_can_go_negative(self):
        a = _agent(down=100)
        recalculate_reputation(a)
        assert a.reputation_score < 0

    def test_terms_combine_additively(self):
        a = _agent(up=3, down=2, cites=4, posts=5)
        recalculate_reputation(a)
        expected = (
            3 * settings.reputation_weight_upvote
            + 4 * settings.reputation_weight_citation
            - 2 * settings.reputation_weight_downvote
            + 5 * settings.reputation_weight_post
        )
        assert a.reputation_score == expected

    def test_a_citation_outweighs_an_upvote(self):
        """Not arithmetic — a claim about what the forum values. If this ever
        flips, the ranking changed and someone should have decided that."""
        assert settings.reputation_weight_citation > settings.reputation_weight_upvote


class TestPercentageHelper:
    def test_zero_total_does_not_raise(self):
        assert _pct(5, 0) == 0.0

    def test_none_part_does_not_raise(self):
        assert _pct(None, 10) == 0.0

    def test_zero_part_is_zero(self):
        assert _pct(0, 10) == 0.0

    def test_ordinary_percentage(self):
        assert _pct(1, 4) == 25.0

    def test_rounds_to_one_decimal(self):
        assert _pct(1, 3) == 33.3

    def test_full_is_one_hundred(self):
        assert _pct(7, 7) == 100.0


class TestInviteToken:
    """The one secret-generator the earlier suite skipped, though it covered the
    other two. Same class, same failure consequences."""

    def test_carries_the_configured_prefix(self):
        assert generate_invite_token().startswith(settings.invite_token_prefix)

    def test_has_192_bits_of_body(self):
        body = generate_invite_token()[len(settings.invite_token_prefix) :]
        assert len(body) == 48  # 24 bytes hex-encoded

    def test_tokens_are_not_repeated(self):
        assert len({generate_invite_token() for _ in range(200)}) == 200

    def test_does_not_collide_with_the_api_key_namespace(self):
        """Distinct prefixes are what let a leaked string be identified by type."""
        assert settings.invite_token_prefix != settings.api_key_prefix
        assert settings.invite_token_prefix != settings.reset_token_prefix
