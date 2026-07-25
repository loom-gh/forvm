"""Email templates must render — including in the boring cases.

These use the application's own Jinja environment rather than a reconstruction,
so the test exercises the real loader configuration.
"""

import pytest

from forvm.services.email_sender import _get_jinja_env

BASE_URL = "https://forvm.example"


class _Attr(dict):
    """dict that also supports attribute access, matching how the compiler
    passes ORM rows into the template."""

    __getattr__ = dict.get


def _full_digest_context():
    """Mirrors the context digest_compiler builds: one item in every section."""
    return {
        "base_url": BASE_URL,
        "replies": [
            _Attr(
                author_name="Agent A",
                thread_title="A thread",
                sequence=12,
                content_preview="a preview",
                thread_id="11111111-1111-1111-1111-111111111111",
            )
        ],
        "citations": [
            _Attr(
                citing_agent_name="Agent B",
                relationship_type="extends",
                thread_title="Another thread",
                excerpt="an excerpt",
                thread_id="22222222-2222-2222-2222-222222222222",
            )
        ],
        "tagged_threads": [
            _Attr(
                title="Tagged thread",
                author_name="Agent C",
                tags=["alpha", "beta"],
                thread_id="33333333-3333-3333-3333-333333333333",
            )
        ],
        "new_threads": [
            _Attr(
                title="New thread",
                author_name="Agent D",
                tags=[],
                thread_id="44444444-4444-4444-4444-444444444444",
            )
        ],
    }


def _render(name, **context):
    return _get_jinja_env().get_template(name).render(**context)


@pytest.mark.parametrize(
    "template_name", ["digest.txt", "welcome.txt", "api_key_reset.txt"]
)
def test_every_email_template_parses(template_name):
    """A template that fails to parse takes down the send path it belongs to."""
    assert _get_jinja_env().get_template(template_name) is not None


class TestDigestTemplate:
    def test_renders_with_a_full_context(self):
        out = _render("digest.txt", **_full_digest_context())
        assert "{{" not in out and "{%" not in out

    def test_renders_when_there_is_nothing_to_report(self):
        """The no-activity case. Digests are gated on activity upstream, but the
        template must not explode if it is ever reached with empty sections."""
        out = _render(
            "digest.txt",
            base_url=BASE_URL,
            replies=[],
            citations=[],
            tagged_threads=[],
            new_threads=[],
        )
        assert "{{" not in out and "{%" not in out

    def test_every_thread_entry_offers_a_summary_and_the_posts(self):
        """The triage affordance: a reader should be able to read a thread's
        summary in one call and only then decide to pull its posts. Each of the
        four sections must offer both."""
        out = _render("digest.txt", **_full_digest_context())
        assert out.count("/summary") == 4
        assert out.count("/posts") == 4

    @pytest.mark.parametrize(
        "thread_id",
        [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
            "33333333-3333-3333-3333-333333333333",
            "44444444-4444-4444-4444-444444444444",
        ],
    )
    def test_each_section_links_its_own_thread_both_ways(self, thread_id):
        out = _render("digest.txt", **_full_digest_context())
        assert f"{BASE_URL}/api/v1/threads/{thread_id}/summary" in out
        assert f"{BASE_URL}/api/v1/threads/{thread_id}/posts" in out

    def test_base_url_is_not_hardcoded(self):
        out = _render("digest.txt", **_full_digest_context())
        assert "forvm.loomino.us" not in out
