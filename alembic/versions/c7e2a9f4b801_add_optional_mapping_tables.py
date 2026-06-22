"""add optional mapping tables (Geography Mapping module)

Revision ID: c7e2a9f4b801
Revises: f1a2b3c4d5e6
Create Date: 2026-06-19 12:00:00.000000

Adds the two tables backing the Geography Mapping module (spec task 10, R10):

* ``optional_map_locations`` — a place a student must identify, with the short
  UPSC-style "what to know" ``detail`` shown on click (R10.3), filed under a
  feature ``category`` (river / plateau / plain / …).
* ``optional_map_questions`` — previous-year map-based questions organized
  ``category``-wise across years (R10.1, R10.2), optionally linked to a location.

Both carry a ``review_status`` (enum ``optionalreviewstatusenum``, already
created by revision ``e93f3dcfde5b``) so draft/seeded mapping content stays
gated from students until reviewed (R17.2, R17.3, design Property 8).

Isolation (Requirement 2 / design Property 9): this migration ONLY creates new
``optional_*`` tables. It does NOT touch GS Geography or any existing table, so
it is fully reversible by dropping the two new tables.

Requirements: 10.1, 10.2, 10.3, 10.4, 17.2, 17.3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7e2a9f4b801"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The enum type already exists (created with optional_content_units in revision
# e93f3dcfde5b). ``create_type=False`` prevents Postgres from re-creating it; it
# is a no-op on SQLite.
_REVIEW_STATUS_ENUM = sa.Enum(
    "UNREVIEWED",
    "IN_REVIEW",
    "REVIEWED",
    name="optionalreviewstatusenum",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "optional_map_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("authored", sa.Boolean(), nullable=False),
        sa.Column("review_status", _REVIEW_STATUS_ENUM, nullable=False),
        # Audit + soft-delete mixin columns.
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["optional_subjects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_optional_map_locations_id"), "optional_map_locations", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_optional_map_locations_subject_id"),
        "optional_map_locations",
        ["subject_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_map_locations_name"), "optional_map_locations", ["name"], unique=False
    )
    op.create_index(
        op.f("ix_optional_map_locations_category"),
        "optional_map_locations",
        ["category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_map_locations_review_status"),
        "optional_map_locations",
        ["review_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_map_locations_is_deleted"),
        "optional_map_locations",
        ["is_deleted"],
        unique=False,
    )

    op.create_table(
        "optional_map_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=True),
        sa.Column("beyond_syllabus", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("review_status", _REVIEW_STATUS_ENUM, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["optional_subjects.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["optional_map_locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_optional_map_questions_id"), "optional_map_questions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_optional_map_questions_subject_id"),
        "optional_map_questions",
        ["subject_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_map_questions_location_id"),
        "optional_map_questions",
        ["location_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_map_questions_year"), "optional_map_questions", ["year"], unique=False
    )
    op.create_index(
        op.f("ix_optional_map_questions_category"),
        "optional_map_questions",
        ["category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_map_questions_review_status"),
        "optional_map_questions",
        ["review_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("optional_map_questions")
    op.drop_table("optional_map_locations")
