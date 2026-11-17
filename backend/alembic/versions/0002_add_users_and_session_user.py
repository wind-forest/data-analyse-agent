"""add users and session.user_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"])

    op.add_column("sessions", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_foreign_key(
        op.f("fk_sessions_user_id_users"),
        "sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_sessions_user_id_users"), "sessions", type_="foreignkey")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_column("sessions", "user_id")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
