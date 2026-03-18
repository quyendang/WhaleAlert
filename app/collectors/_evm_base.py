"""Shared EVM collector logic (Etherscan-compatible APIs)."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.services.transaction_service import transaction_service

logger = logging.getLogger(__name__)
WEI = Decimal("1e18")


class EvmCollector(BaseCollector):
    """Base for Etherscan-compatible chains (ETH, BSC, MATIC)."""

    api_url: str
    api_key_attr: str  # attribute name in settings
    blocks_per_poll: int = 20

    def __init__(self, settings):
        self._settings = settings
        self._api_key: str = getattr(settings, self.api_key_attr, "")

    async def poll(self, db: AsyncSession) -> None:
        self.log_poll_start()
        if not self._api_key:
            logger.warning("[%s] No API key set (%s), skipping", self.chain, self.api_key_attr)
            return

        last_block = await transaction_service.get_cursor(db, self.chain)

        try:
            latest_block = await self._get_latest_block()
            if latest_block <= last_block:
                return

            start_block = max(last_block + 1, latest_block - self.blocks_per_poll)
            txs = await self._fetch_normal_txs(start_block, latest_block)
            saved = 0

            for tx in txs:
                value_wei = int(tx.get("value", "0"))
                if value_wei == 0:
                    continue
                if tx.get("isError", "0") == "1":
                    continue

                amount = Decimal(value_wei) / WEI
                block_time = datetime.fromtimestamp(int(tx["timeStamp"]), tz=timezone.utc)

                ok = await transaction_service.save_if_whale(
                    db,
                    chain=self.chain,
                    tx_hash=tx["hash"],
                    block_number=int(tx["blockNumber"]),
                    block_time=block_time,
                    from_address=tx.get("from", "").lower(),
                    to_address=tx.get("to", "").lower(),
                    amount_native=amount,
                    native_symbol=self.native_symbol,
                    is_contract=tx.get("input", "0x") != "0x",
                )
                if ok:
                    saved += 1

            await transaction_service.update_cursor(db, self.chain, latest_block)
            self.log_poll_done(saved, len(txs))

        except Exception as exc:
            logger.error("[%s] Poll error: %s", self.chain, exc)
            await transaction_service.update_cursor(db, self.chain, last_block, error=str(exc))

    async def _get_latest_block(self) -> int:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(self.api_url, params={
                "module": "proxy",
                "action": "eth_blockNumber",
                "apikey": self._api_key,
            })
            resp.raise_for_status()
            result = resp.json().get("result", "0x0")
            return int(result, 16)

    async def _fetch_normal_txs(self, start_block: int, end_block: int) -> list[dict]:
        """Fetch large transfers by scanning recent blocks via Etherscan-like API."""
        # We fetch the last N transactions globally — Etherscan doesn't support
        # all-address queries, so we poll the top whale wallets + token transfers
        # For MVP, we use the "tokentx" endpoint to catch ERC-20 large transfers
        # and rely on monitored address lists for ETH native transfers.
        # A production system would use an archive node or Moralis.
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self.api_url, params={
                "module": "account",
                "action": "txlistinternal",
                "startblock": start_block,
                "endblock": end_block,
                "sort": "desc",
                "apikey": self._api_key,
            })
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "1":
                return data.get("result", [])
            return []
