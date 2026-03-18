"""Ethereum whale collector using Etherscan API."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.config import get_settings
from app.services.transaction_service import transaction_service

logger = logging.getLogger(__name__)
WEI = Decimal("1e18")
ETHERSCAN_URL = "https://api.etherscan.io/api"


class EthCollector(BaseCollector):
    chain = "ETH"
    native_symbol = "ETH"

    def __init__(self):
        self._settings = get_settings()

    async def poll(self, db: AsyncSession) -> None:
        self.log_poll_start()
        api_key = self._settings.etherscan_api_key
        if not api_key:
            logger.warning("[ETH] No ETHERSCAN_API_KEY set, skipping")
            return

        last_block = await transaction_service.get_cursor(db, self.chain)

        try:
            # Get latest block number
            latest_block = await self._get_latest_block(api_key)
            if latest_block <= last_block:
                return

            start_block = max(last_block + 1, latest_block - 20)  # max 20 blocks lookback

            txs = await self._fetch_transactions(api_key, start_block, latest_block)
            saved = 0
            for tx in txs:
                value_wei = int(tx.get("value", "0"))
                if value_wei == 0:
                    continue

                amount_eth = Decimal(value_wei) / WEI
                block_time = datetime.fromtimestamp(int(tx["timeStamp"]), tz=timezone.utc)
                is_contract = tx.get("input", "0x") != "0x"

                ok = await transaction_service.save_if_whale(
                    db,
                    chain=self.chain,
                    tx_hash=tx["hash"],
                    block_number=int(tx["blockNumber"]),
                    block_time=block_time,
                    from_address=tx.get("from", "").lower(),
                    to_address=tx.get("to", "").lower(),
                    amount_native=amount_eth,
                    native_symbol=self.native_symbol,
                    is_contract=is_contract,
                )
                if ok:
                    saved += 1

            await transaction_service.update_cursor(db, self.chain, latest_block)
            self.log_poll_done(saved, len(txs))

        except Exception as exc:
            logger.error("[ETH] Poll error: %s", exc)
            await transaction_service.update_cursor(db, self.chain, last_block, error=str(exc))

    async def _get_latest_block(self, api_key: str) -> int:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(ETHERSCAN_URL, params={
                "module": "proxy",
                "action": "eth_blockNumber",
                "apikey": api_key,
            })
            resp.raise_for_status()
            return int(resp.json()["result"], 16)

    async def _fetch_transactions(self, api_key: str, start_block: int, end_block: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ETHERSCAN_URL, params={
                "module": "account",
                "action": "txlist",
                "address": "0x0000000000000000000000000000000000000000",  # dummy - fetch all
                "startblock": start_block,
                "endblock": end_block,
                "sort": "asc",
                "apikey": api_key,
            })
            # Etherscan doesn't support all-tx query without address, so use internal tx endpoint
            # Use token transfer approach instead
            resp2 = await client.get(ETHERSCAN_URL, params={
                "module": "account",
                "action": "txlistinternal",
                "startblock": start_block,
                "endblock": end_block,
                "sort": "asc",
                "apikey": api_key,
            })
            resp2.raise_for_status()
            data = resp2.json()
            if data.get("status") == "1":
                return data.get("result", [])
            return []
