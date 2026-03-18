"""Solana whale collector using public Solana RPC."""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.services.transaction_service import transaction_service

logger = logging.getLogger(__name__)
LAMPORTS = Decimal("1e9")

# Public RPC endpoints — tried in order; falls back if one rate-limits
SOL_RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana-mainnet.g.alchemy.com/v2/demo",  # Alchemy public demo
]


class SolCollector(BaseCollector):
    chain = "SOL"
    native_symbol = "SOL"

    async def poll(self, db: AsyncSession) -> None:
        self.log_poll_start()
        last_block = await transaction_service.get_cursor(db, self.chain)

        try:
            current_slot = await self._get_slot()
            if current_slot <= last_block:
                return

            signatures = await self._get_recent_signatures(limit=50)
            saved = 0

            for sig_info in signatures:
                sig = sig_info.get("signature")
                if not sig:
                    continue
                slot = sig_info.get("slot", 0)
                if slot <= last_block:
                    continue

                tx = await self._get_transaction(sig)
                if not tx:
                    continue

                lamports = self._extract_lamport_transfer(tx)
                if lamports <= 0:
                    continue

                amount_sol = Decimal(lamports) / LAMPORTS
                block_time_ts = tx.get("blockTime") or sig_info.get("blockTime", 0)
                if not block_time_ts:
                    continue
                block_time = datetime.fromtimestamp(block_time_ts, tz=timezone.utc)

                accounts = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
                from_addr = accounts[0] if accounts else None
                to_addr = accounts[1] if len(accounts) > 1 else None

                ok = await transaction_service.save_if_whale(
                    db,
                    chain=self.chain,
                    tx_hash=sig,
                    block_number=slot,
                    block_time=block_time,
                    from_address=from_addr,
                    to_address=to_addr,
                    amount_native=amount_sol,
                    native_symbol=self.native_symbol,
                )
                if ok:
                    saved += 1

            await transaction_service.update_cursor(db, self.chain, current_slot)
            self.log_poll_done(saved, len(signatures))

        except Exception as exc:
            logger.error("[SOL] Poll error: %s", exc)
            await transaction_service.update_cursor(db, self.chain, last_block, error=str(exc))

    # ── RPC helpers with retry + fallback ────────────────────────────────────

    async def _rpc_post(self, payload: dict, retries: int = 3) -> dict | None:
        """POST to Solana RPC with retry/backoff and endpoint fallback on 429."""
        for endpoint in SOL_RPC_ENDPOINTS:
            for attempt in range(retries):
                try:
                    async with httpx.AsyncClient(timeout=12) as client:
                        resp = await client.post(endpoint, json=payload)

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        logger.debug("[SOL] 429 on %s — backing off %ds", endpoint, wait)
                        await asyncio.sleep(wait)
                        continue

                    if resp.status_code == 200:
                        return resp.json()

                except httpx.TimeoutException:
                    if attempt < retries - 1:
                        await asyncio.sleep(1)
                except Exception as exc:
                    logger.debug("[SOL] RPC error on %s: %s", endpoint, exc)
                    break  # try next endpoint

            # If we exhausted retries on this endpoint, try next endpoint
        logger.warning("[SOL] All RPC endpoints failed for method=%s", payload.get("method"))
        return None

    async def _get_slot(self) -> int:
        data = await self._rpc_post({"jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": []})
        return data.get("result", 0) if data else 0

    async def _get_recent_signatures(self, limit: int = 50) -> list[dict]:
        """Fetch recent signatures from known high-volume exchange accounts."""
        known_accounts = [
            "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",  # Binance SOL hot wallet
            "5tzFkiKscXHK5ZXCGbXZxdw7gtrjzgQpv4er7QfYKDSF",  # Huobi SOL
        ]
        all_sigs: list[dict] = []
        per_account = max(1, limit // len(known_accounts))
        for account in known_accounts:
            data = await self._rpc_post({
                "jsonrpc": "2.0", "id": 1,
                "method": "getSignaturesForAddress",
                "params": [account, {"limit": per_account}],
            })
            if data:
                all_sigs.extend(data.get("result", []))
        return all_sigs

    async def _get_transaction(self, signature: str) -> dict | None:
        data = await self._rpc_post({
            "jsonrpc": "2.0", "id": 1,
            "method": "getTransaction",
            "params": [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}],
        })
        return data.get("result") if data else None

    def _extract_lamport_transfer(self, tx: dict) -> int:
        """Return the largest absolute balance change across all accounts in the tx."""
        meta = tx.get("meta", {})
        pre = meta.get("preBalances", [])
        post = meta.get("postBalances", [])
        if not pre or not post:
            return 0
        return max(
            (abs(pre[i] - post[i]) for i in range(min(len(pre), len(post)))),
            default=0,
        )
