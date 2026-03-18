"""Whale transaction persistence service."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.transaction import ChainCursor, WhaleTransaction
from app.services.label_service import get_label
from app.services.price_service import price_service

logger = logging.getLogger(__name__)
settings = get_settings()


class TransactionService:
    async def save_if_whale(
        self,
        db: AsyncSession,
        *,
        chain: str,
        tx_hash: str,
        block_number: int | None,
        block_time: datetime,
        from_address: str | None,
        to_address: str | None,
        amount_native: Decimal,
        native_symbol: str,
        tx_type: str = "transfer",
        is_contract: bool = False,
    ) -> bool:
        """
        Check if transaction meets whale threshold, then upsert into DB.
        Returns True if saved, False if below threshold or duplicate.
        """
        usd_price = price_service.get_usd_price(native_symbol)
        if usd_price is None:
            logger.debug("No price for %s, skipping tx %s", native_symbol, tx_hash[:10])
            return False

        amount_usd = amount_native * Decimal(str(usd_price))
        threshold = settings.whale_thresholds.get(chain, 500_000)

        if amount_usd < threshold:
            return False

        from_label = get_label(from_address or "")
        to_label = get_label(to_address or "")

        # Classify tx type based on labels
        if tx_type == "transfer":
            if to_label != "Unknown":
                tx_type = "exchange_deposit"
            elif from_label != "Unknown":
                tx_type = "exchange_withdrawal"

        stmt = text("""
            INSERT INTO whale_transactions
                (tx_hash, chain, block_number, block_time, from_address, to_address,
                 from_label, to_label, amount_native, native_symbol, amount_usd,
                 usd_price_used, tx_type, is_contract)
            VALUES
                (:tx_hash, :chain, :block_number, :block_time, :from_address, :to_address,
                 :from_label, :to_label, :amount_native, :native_symbol, :amount_usd,
                 :usd_price_used, :tx_type, :is_contract)
            ON CONFLICT ON CONSTRAINT uq_wt_hash_chain DO NOTHING
        """)

        result = await db.execute(
            stmt,
            {
                "tx_hash": tx_hash,
                "chain": chain,
                "block_number": block_number,
                "block_time": block_time,
                "from_address": from_address,
                "to_address": to_address,
                "from_label": from_label,
                "to_label": to_label,
                "amount_native": str(amount_native),
                "native_symbol": native_symbol,
                "amount_usd": str(amount_usd.quantize(Decimal("0.01"))),
                "usd_price_used": str(Decimal(str(usd_price))),
                "tx_type": tx_type,
                "is_contract": is_contract,
            },
        )
        await db.commit()

        inserted = result.rowcount > 0
        if inserted:
            logger.info(
                "Whale tx saved: %s %s %s %s ($%s)",
                chain, native_symbol, float(amount_native), tx_hash[:12], int(amount_usd)
            )
        return inserted

    async def update_cursor(
        self,
        db: AsyncSession,
        chain: str,
        last_block: int,
        error: str | None = None,
    ) -> None:
        if error:
            stmt = text("""
                UPDATE chain_cursors
                SET error_count = error_count + 1,
                    last_error = :error,
                    last_polled_at = :now
                WHERE chain = :chain
            """)
            await db.execute(stmt, {"chain": chain, "error": error, "now": datetime.now(timezone.utc)})
        else:
            stmt = text("""
                UPDATE chain_cursors
                SET last_block = :last_block,
                    last_polled_at = :now,
                    error_count = 0,
                    last_error = NULL
                WHERE chain = :chain
            """)
            await db.execute(stmt, {"chain": chain, "last_block": last_block, "now": datetime.now(timezone.utc)})
        await db.commit()

    async def get_cursor(self, db: AsyncSession, chain: str) -> int:
        result = await db.execute(
            text("SELECT last_block FROM chain_cursors WHERE chain = :chain"),
            {"chain": chain},
        )
        row = result.fetchone()
        return row[0] if row else 0


transaction_service = TransactionService()
