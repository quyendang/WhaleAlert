"""BSC (BNB Chain) whale collector using BSCScan API."""
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
BSCSCAN_URL = "https://api.bscscan.com/api"


class BscCollector(BaseCollector):
    chain = "BSC"
    native_symbol = "BNB"

    def __init__(self):
        self._settings = get_settings()

    async def poll(self, db: AsyncSession) -> None:
        self.log_poll_start()
        api_key = self._settings.bscscan_api_key
        if not api_key:
            logger.warning("[BSC] No BSCSCAN_API_KEY set, skipping")
            return

        last_block = await transaction_service.get_cursor(db, self.chain)

        try:
            latest_block = await self._get_latest_block(api_key)
            if latest_block <= last_block:
                return

            start_block = max(last_block + 1, latest_block - 20)
            txs = await self._fetch_transactions(api_key, start_block, latest_block)
            saved = 0

            for tx in txs:
                value_wei = int(tx.get("value", "0"))
                if value_wei == 0 or tx.get("isError", "0") == "1":
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
            logger.error("[BSC] Poll error: %s", exc)
            await transaction_service.update_cursor(db, self.chain, last_block, error=str(exc))

    async def _get_latest_block(self, api_key: str) -> int:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BSCSCAN_URL, params={
                "module": "proxy", "action": "eth_blockNumber", "apikey": api_key,
            })
            resp.raise_for_status()
            return int(resp.json()["result"], 16)

    async def _fetch_transactions(self, api_key: str, start: int, end: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(BSCSCAN_URL, params={
                "module": "account", "action": "txlistinternal",
                "startblock": start, "endblock": end,
                "sort": "desc", "apikey": api_key,
            })
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", []) if data.get("status") == "1" else []
