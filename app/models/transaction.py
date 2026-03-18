from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WhaleTransaction(Base):
    __tablename__ = "whale_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Identity / dedup
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    chain: Mapped[str] = mapped_column(String(16), nullable=False)

    # Timing
    block_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    block_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Parties
    from_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    from_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_label: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Amounts
    amount_native: Mapped[Decimal] = mapped_column(Numeric(36, 10), nullable=False)
    native_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    usd_price_used: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    # Classification
    tx_type: Mapped[str] = mapped_column(String(32), nullable=False, default="transfer")
    is_contract: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("uq_wt_hash_chain", "tx_hash", "chain", unique=True),
        Index("idx_wt_chain_time", "chain", "block_time"),
        Index("idx_wt_detected", "detected_at"),
        Index("idx_wt_usd", "amount_usd"),
        Index("idx_wt_from", "from_address"),
        Index("idx_wt_to", "to_address"),
    )


class ChainCursor(Base):
    __tablename__ = "chain_cursors"

    chain: Mapped[str] = mapped_column(String(16), primary_key=True)
    last_block: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
