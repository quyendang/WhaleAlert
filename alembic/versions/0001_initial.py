"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whale_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tx_hash", sa.String(128), nullable=False),
        sa.Column("chain", sa.String(16), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=True),
        sa.Column("block_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("from_address", sa.String(128), nullable=True),
        sa.Column("to_address", sa.String(128), nullable=True),
        sa.Column("from_label", sa.String(64), nullable=True),
        sa.Column("to_label", sa.String(64), nullable=True),
        sa.Column("amount_native", sa.Numeric(36, 10), nullable=False),
        sa.Column("native_symbol", sa.String(16), nullable=False),
        sa.Column("amount_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("usd_price_used", sa.Numeric(20, 6), nullable=True),
        sa.Column("tx_type", sa.String(32), nullable=False, server_default="transfer"),
        sa.Column("is_contract", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_wt_hash_chain", "whale_transactions", ["tx_hash", "chain"], unique=True)
    op.create_index("idx_wt_chain_time", "whale_transactions", ["chain", "block_time"])
    op.create_index("idx_wt_detected", "whale_transactions", ["detected_at"])
    op.create_index("idx_wt_usd", "whale_transactions", ["amount_usd"])
    op.create_index("idx_wt_from", "whale_transactions", ["from_address"])
    op.create_index("idx_wt_to", "whale_transactions", ["to_address"])

    op.create_table(
        "chain_cursors",
        sa.Column("chain", sa.String(16), nullable=False),
        sa.Column("last_block", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("chain"),
    )


def downgrade() -> None:
    op.drop_table("chain_cursors")
    op.drop_index("idx_wt_to")
    op.drop_index("idx_wt_from")
    op.drop_index("idx_wt_usd")
    op.drop_index("idx_wt_detected")
    op.drop_index("idx_wt_chain_time")
    op.drop_index("uq_wt_hash_chain")
    op.drop_table("whale_transactions")
