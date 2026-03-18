"""Bitcoin whale collector using Blockstream API (no API key required)."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.services.transaction_service import transaction_service

logger = logging.getLogger(__name__)
SATOSHI = Decimal("1e8")
BLOCKSTREAM_URL = "https://blockstream.info/api"


class BtcCollector(BaseCollector):
    chain = "BTC"
    native_symbol = "BTC"

    async def poll(self, db: AsyncSession) -> None:
        self.log_poll_start()
        last_block = await transaction_service.get_cursor(db, self.chain)

        try:
            tip = await self._get_tip()
            if tip["height"] <= last_block:
                return

            # Scan last 3 blocks
            start_height = max(last_block + 1, tip["height"] - 2)
            saved = 0
            scanned = 0

            for height in range(start_height, tip["height"] + 1):
                block_hash = await self._get_block_hash(height)
                if not block_hash:
                    continue
                block_txs = await self._get_block_txs(block_hash)
                block_time = datetime.fromtimestamp(
                    await self._get_block_time(block_hash), tz=timezone.utc
                )

                for tx in block_txs:
                    scanned += 1
                    total_out = sum(
                        vout.get("value", 0)
                        for vout in tx.get("vout", [])
                        if not vout.get("scriptpubkey_type") == "op_return"
                    )
                    if total_out == 0:
                        continue

                    amount_btc = Decimal(total_out) / SATOSHI
                    from_addr = self._get_first_input_addr(tx)
                    to_addr = self._get_first_output_addr(tx)

                    ok = await transaction_service.save_if_whale(
                        db,
                        chain=self.chain,
                        tx_hash=tx["txid"],
                        block_number=height,
                        block_time=block_time,
                        from_address=from_addr,
                        to_address=to_addr,
                        amount_native=amount_btc,
                        native_symbol=self.native_symbol,
                    )
                    if ok:
                        saved += 1

            await transaction_service.update_cursor(db, self.chain, tip["height"])
            self.log_poll_done(saved, scanned)

        except Exception as exc:
            logger.error("[BTC] Poll error: %s", exc)
            await transaction_service.update_cursor(db, self.chain, last_block, error=str(exc))

    async def _get_tip(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BLOCKSTREAM_URL}/blocks/tip")
            resp.raise_for_status()
            return resp.json()

    async def _get_block_hash(self, height: int) -> str | None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BLOCKSTREAM_URL}/block-height/{height}")
            if resp.status_code == 200:
                return resp.text.strip()
        return None

    async def _get_block_time(self, block_hash: str) -> int:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BLOCKSTREAM_URL}/block/{block_hash}")
            resp.raise_for_status()
            return resp.json().get("timestamp", 0)

    async def _get_block_txs(self, block_hash: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{BLOCKSTREAM_URL}/block/{block_hash}/txs")
            if resp.status_code == 200:
                return resp.json()
        return []

    def _get_first_input_addr(self, tx: dict) -> str | None:
        for vin in tx.get("vin", []):
            addr = vin.get("prevout", {}).get("scriptpubkey_address")
            if addr:
                return addr
        return None

    def _get_first_output_addr(self, tx: dict) -> str | None:
        for vout in tx.get("vout", []):
            addr = vout.get("scriptpubkey_address")
            if addr:
                return addr
        return None
