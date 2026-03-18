"""TRON whale collector using TronGrid API."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.config import get_settings
from app.services.transaction_service import transaction_service

logger = logging.getLogger(__name__)
SUN = Decimal("1e6")  # 1 TRX = 1,000,000 SUN
TRONGRID_URL = "https://api.trongrid.io"


class TrxCollector(BaseCollector):
    chain = "TRX"
    native_symbol = "TRX"

    def __init__(self):
        self._settings = get_settings()

    async def poll(self, db: AsyncSession) -> None:
        self.log_poll_start()
        last_block = await transaction_service.get_cursor(db, self.chain)

        try:
            latest_block = await self._get_latest_block()
            if latest_block <= last_block:
                return

            txs = await self._fetch_transactions()
            saved = 0

            for tx in txs:
                raw_data = tx.get("raw_data", {})
                contracts = raw_data.get("contract", [])
                if not contracts:
                    continue

                contract = contracts[0]
                if contract.get("type") != "TransferContract":
                    continue

                value_data = contract.get("parameter", {}).get("value", {})
                amount_sun = value_data.get("amount", 0)
                if amount_sun <= 0:
                    continue

                amount_trx = Decimal(amount_sun) / SUN
                timestamp_ms = raw_data.get("timestamp", 0)
                block_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

                from_addr = value_data.get("owner_address", "")
                to_addr = value_data.get("to_address", "")

                ok = await transaction_service.save_if_whale(
                    db,
                    chain=self.chain,
                    tx_hash=tx.get("txID", ""),
                    block_number=latest_block,
                    block_time=block_time,
                    from_address=from_addr,
                    to_address=to_addr,
                    amount_native=amount_trx,
                    native_symbol=self.native_symbol,
                )
                if ok:
                    saved += 1

            await transaction_service.update_cursor(db, self.chain, latest_block)
            self.log_poll_done(saved, len(txs))

        except Exception as exc:
            logger.error("[TRX] Poll error: %s", exc)
            await transaction_service.update_cursor(db, self.chain, last_block, error=str(exc))

    async def _get_latest_block(self) -> int:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {}
            if self._settings.trongrid_api_key:
                headers["TRON-PRO-API-KEY"] = self._settings.trongrid_api_key
            resp = await client.post(
                f"{TRONGRID_URL}/wallet/getnowblock",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("block_header", {}).get("raw_data", {}).get("number", 0)

    async def _fetch_transactions(self, limit: int = 50) -> list[dict]:
        """Fetch recent TRX transfers from known high-volume exchange addresses."""
        known_addresses = [
            "TKkeiboTkxXKJpbmVFbv4a8ov5rAfRDMf9",  # Binance TRX hot wallet
            "TVj7RNVHy6thbM7BWdSe9G6gXwKhjhdNZS",  # Binance cold
        ]
        headers = {"Accept": "application/json"}
        if self._settings.trongrid_api_key:
            headers["TRON-PRO-API-KEY"] = self._settings.trongrid_api_key

        per_address = max(1, limit // len(known_addresses))
        all_txs: list[dict] = []

        async with httpx.AsyncClient(timeout=15) as client:
            for address in known_addresses:
                resp = await client.get(
                    f"{TRONGRID_URL}/v1/accounts/{address}/transactions",
                    params={"limit": per_address, "only_confirmed": "true"},
                    headers=headers,
                )
                if resp.status_code == 200:
                    all_txs.extend(resp.json().get("data", []))
        return all_txs
