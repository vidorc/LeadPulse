"""ingestion columns: org ingest_secret + lead idempotency_key

The ingestion service authenticates inbound webhooks with a per-org HMAC
secret (``organizations.ingest_secret``) and deduplicates repeated channel
deliveries by ``leads.idempotency_key``. Both columns were added to the models
but never migrated, so autogenerate reported drift after the revenue-recovery
tables landed.

``ingest_secret`` is NOT NULL with no server default (``signup`` mints one via
``secrets.token_urlsafe``). To stay safe against any pre-existing org rows, the
column is added nullable, every existing row is backfilled with its own random
secret, and only then is NOT NULL enforced — never a single shared default.

Revision ID: c3a8e5f1d6b7
Revises: b2f1c7d9e3a4
Create Date: 2026-05-31 14:10:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3a8e5f1d6b7"
down_revision: Union[str, None] = "b2f1c7d9e3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # leads.idempotency_key — nullable, indexed (per-org dedupe key).
    op.add_column(
        "leads",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_leads_idempotency_key"), "leads", ["idempotency_key"], unique=False
    )

    # organizations.ingest_secret — NOT NULL, but back-compatible:
    # add nullable, give each existing org its own random secret, then enforce.
    op.add_column(
        "organizations",
        sa.Column("ingest_secret", sa.String(length=64), nullable=True),
    )
    # gen_random_uuid() is built into PostgreSQL 13+ (no extension needed);
    # 32 hex chars is a distinct, unguessable per-row secret for any backfill.
    op.execute(
        "UPDATE organizations "
        "SET ingest_secret = replace(gen_random_uuid()::text, '-', '') "
        "WHERE ingest_secret IS NULL"
    )
    op.alter_column("organizations", "ingest_secret", nullable=False)


def downgrade() -> None:
    op.drop_column("organizations", "ingest_secret")
    op.drop_index(op.f("ix_leads_idempotency_key"), table_name="leads")
    op.drop_column("leads", "idempotency_key")
