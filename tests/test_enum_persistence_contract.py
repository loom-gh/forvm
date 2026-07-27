"""The enum contract the database actually depends on.

SQLAlchemy's PgEnum persists the Python enum's **.name**, not its .value. This is
not a guess — it is recorded in `alembic/versions/ccc17da65492_fix_notification_kind_enum_case.py`,
whose docstring says:

    Add uppercase enum values to match PgEnum .name serialization. Prior
    migrations added lowercase values ('thread_digest', 'digest', 'welcome')
    but SQLAlchemy PgEnum persists the Python enum .name (uppercase). The
    lowercase values remain but are unused.

So this project has already been bitten once by the name-vs-value ambiguity in
exactly these enums, and the repair was to add *both* casings to the Postgres type.
The lowercase labels are still there, unused — which means a future change that
silently flipped persistence from .name to .value would NOT fail loudly. It would
start writing valid-but-different labels and split the data in two.

That is the failure these tests exist to make noisy. Renaming a member, reordering
in a way that changes .name, or migrating the base class (see the UP042 entry in
pyproject.toml) must break a test here rather than a production row.

No database required — this pins the Python side of the contract.
"""

from typing import ClassVar

import pytest

from forvm.models.notification import DeliveryChannel, DeliveryStatus, NotificationKind
from forvm.models.thread import ThreadStatus

PERSISTED_ENUMS = [NotificationKind, DeliveryChannel, DeliveryStatus, ThreadStatus]


@pytest.mark.parametrize("enum_cls", PERSISTED_ENUMS, ids=lambda e: e.__name__)
class TestPersistedEnumContract:
    def test_names_are_uppercase(self, enum_cls):
        """PgEnum writes .name. The DB labels are uppercase, so the names must be."""
        for member in enum_cls:
            assert member.name == member.name.upper(), (
                f"{enum_cls.__name__}.{member.name} is not uppercase; "
                "PgEnum persists .name and the DB labels are uppercase"
            )

    def test_names_are_unique_case_insensitively(self, enum_cls):
        """Two members differing only by case would collide in the DB type."""
        lowered = [m.name.lower() for m in enum_cls]
        assert len(lowered) == len(set(lowered))

    def test_name_and_value_are_distinguishable(self, enum_cls):
        """The whole hazard is that .name and .value differ for these enums. If a
        refactor ever made them identical, the ambiguity that caused the case-fix
        migration would become invisible rather than fixed."""
        for member in enum_cls:
            assert member.name != member.value


class TestNotificationKindMembers:
    """Exact names, because these are live labels in a Postgres type. Changing one
    is a migration, not a rename."""

    EXPECTED: ClassVar[frozenset[str]] = frozenset(
        {"THREAD_REPLY", "CITATION", "SITE_DIGEST", "THREAD_DIGEST"}
    )

    def test_known_members_still_present(self):
        names = {m.name for m in NotificationKind}
        missing = self.EXPECTED - names
        assert not missing, f"removed/renamed persisted enum labels: {missing}"

    def test_values_remain_lowercase_snake(self):
        """.value is what the API and templates read; it should stay stable too."""
        for m in NotificationKind:
            assert m.value == m.value.lower()


class TestStrEnumMigrationGuard:
    """Guards the deferred UP042 change.

    These are `(str, Enum)` today. Converting to `enum.StrEnum` changes what
    `str(member)` returns — from 'NotificationKind.THREAD_REPLY' to 'thread_reply'.
    Nothing in the codebase currently interpolates these enums, so the change looks
    safe; this test exists so that if it stops being safe, or if the conversion
    happens, the behaviour change is visible in a test diff rather than in data.
    """

    def test_members_are_str_instances(self):
        """Already true for (str, Enum); must stay true under StrEnum."""
        assert isinstance(NotificationKind.THREAD_REPLY, str)

    def test_str_currently_includes_the_class_name(self):
        """Documents present behaviour. Under StrEnum this becomes 'thread_reply'.
        If this test fails, the base class changed — verify the DB labels and the
        case-fix migration before accepting it."""
        assert str(NotificationKind.THREAD_REPLY) == "NotificationKind.THREAD_REPLY"

    def test_value_access_is_unaffected_either_way(self):
        """.value and .name are the two things persistence and the API rely on, and
        neither is altered by the base-class choice. This is why the migration is
        probably safe — stated as a test rather than as a comment."""
        assert NotificationKind.THREAD_REPLY.value == "thread_reply"
        assert NotificationKind.THREAD_REPLY.name == "THREAD_REPLY"
