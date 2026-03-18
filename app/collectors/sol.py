"""Solana whale collector using public Solana RPC."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.services.transaction_service import transaction_service

logger = logging.getLogger(__name__)
LAMPORTS = Decimal("1e9")
SOL_RPC = "https://api.mainnet-beta.solana.com"

# Known Solana exchange program addresses
SOLANA_PROGRAMS = {
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Whirlpool",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium",
}


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

            # Fetch recent large transactions via getSignaturesForAddress on system program
            signatures = await self._get_recent_signatures(limit=100)
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

    async def _get_slot(self) -> int:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SOL_RPC, json={
                "jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": []
            })
            resp.raise_for_status()
            return resp.json().get("result", 0)

    async def _get_recent_signatures(self, limit: int = 100) -> list[dict]:
        """Get recent signatures from a large known address (Binance SOL hot wallet)."""
        # Use a well-known high-volume account to capture large transfers
        known_accounts = [
            "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",  # Binance SOL
            "5tzFkiKscXHK5ZXCGbXZxdw7gtrjzgQpv4er7QfYKDSF",  # Huobi SOL
        ]
        all_sigs = []
        async with httpx.AsyncClient(timeout=15) as client:
            for account in known_accounts:
                resp = await client.post(SOL_RPC, json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": [account, {"limit": limit // len(known_accounts)}],
                })
                if resp.status_code == 200:
                    all_sigs.extend(resp.json().get("result", []))
        return all_sigs

    async def _get_transaction(self, signature: str) -> dict | None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SOL_RPC, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTransaction",
                "params": [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}],
            })
            if resp.status_code == 200:
                return resp.json().get("result")
        return None

    def _extract_lamport_transfer(self, tx: dict) -> int:
        """Extract the largest SOL transfer amount from a transaction."""
        meta = tx.get("meta", {})
        pre_balances = meta.get("preBalances", [])
        post_balances = meta.get("postBalances", [])
        if not pre_balances or not post_balances:
            return 0
        # Find the max absolute balance change (excluding fee payer index 0 partially)
        max_change = 0
        for i in range(min(len(pre_balances), len(post_balances))):
            change = abs(pre_balances[i] - post_balances[i])
            if change > max_change:
                max_change = change
        return max_change
