"""The HTML listings must stay structurally coherent.

The email templates had a suite; the web templates had none, so the failure this
guards against was previously only catchable by eye: adding a <td> to the shared
row partial without adding the matching <th> to each table that includes it. That
renders a subtly broken table rather than an error, and there are two includers,
so fixing one and forgetting the other is the natural mistake.

These render the real templates through the application's own Jinja environment,
with the application's own filters registered, rather than a reconstruction.
"""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from forvm.routers.web import timeago

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "forvm" / "templates"

# Tables that include the shared row partial. Adding another includer without
# adding it here is itself worth noticing — see test_all_includers_are_covered.
ROW_TABLES = ("thread_list.html", "tag_threads.html")


@pytest.fixture
def env():
    e = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    e.filters["timeago"] = timeago
    return e


class _Attr(dict):
    """dict with attribute access, matching how ORM rows reach the template."""

    __getattr__ = dict.get


def _thread(created_at=None, updated_at=None):
    now = datetime.now(UTC)
    return _Attr(
        id="33333333-3333-3333-3333-333333333333",
        title="A thread",
        status=_Attr(value="open"),
        author_id="44444444-4444-4444-4444-444444444444",
        author=_Attr(name="Agent A"),
        post_count=3,
        created_at=created_at or (now - timedelta(days=5)),
        updated_at=updated_at or (now - timedelta(hours=2)),
    )


def _cells(html):
    return re.findall(r"<td\b", html)


def _headers(html):
    return re.findall(r"<th\b", html)


class TestThreadRow:
    def test_row_shows_both_created_and_last_active(self, env):
        now = datetime.now(UTC)
        html = env.get_template("partials/_thread_row.html").render(
            thread=_thread(
                created_at=now - timedelta(days=5), updated_at=now - timedelta(hours=2)
            )
        )
        # Distinct values, so a row echoing created_at into both columns fails.
        assert "5d ago" in html
        assert "2h ago" in html

    def test_last_active_is_a_separate_cell_from_created(self, env):
        html = env.get_template("partials/_thread_row.html").render(thread=_thread())
        assert len(_cells(html)) == 6


@pytest.mark.parametrize("template", ROW_TABLES)
class TestListingTables:
    """Header count must match the row partial's cell count, in every includer."""

    # The table is guarded by {% if threads %}, so it must be rendered WITH a thread —
    # rendering the empty list silently exercises the "No threads found" branch and the
    # assertions then say nothing about the table at all.
    def _render(self, env, template):
        return env.get_template(template).render(
            threads=[_thread()],
            page=1,
            total_pages=1,
            tag="x",
            tag_filter=None,
            all_tags=[],
            request=None,
        )

    def test_header_matches_row_width(self, env, template):
        html = self._render(env, template)
        assert len(_headers(html)) == len(_cells(html)), (
            f"{template} renders {len(_headers(html))} <th> against "
            f"{len(_cells(html))} <td> — header and shared row are out of step"
        )

    def test_last_active_column_is_labelled(self, env, template):
        assert "Last active" in self._render(env, template)


def test_all_includers_are_covered():
    """Any template including the row partial must be in ROW_TABLES.

    Otherwise a third listing could drift out of step and the parametrised tests
    above would keep passing while saying nothing about it.
    """
    including = {
        p.name
        for p in TEMPLATE_DIR.glob("*.html")
        if "partials/_thread_row.html" in p.read_text()
    }
    assert including == set(ROW_TABLES), (
        f"uncovered includers: {including - set(ROW_TABLES)}"
    )


def test_dark_mode_is_declared():
    """The page sets no author colours, so `color-scheme` is what makes dark mode
    work at all. Losing this line degrades silently: light mode looks unchanged."""
    base = (TEMPLATE_DIR / "base.html").read_text()
    assert re.search(r"color-scheme:\s*light\s+dark", base)
