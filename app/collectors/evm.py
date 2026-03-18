"""
Unified EVM collector using Etherscan API V2.

Single API key covers ETH (chainid=1), BSC (chainid=56), Polygon (chainid=137)
and 60+ other chains via the `chainid` query parameter.

Data strategy per chain per poll:
  1. eth_blockNumber          → 1 API call  (get current block)
  2. getLogs per token        → N API calls  (ERC-20 Transfer events in block range)
  3. txlist per whale_address → M API calls  (native token transfers from known exchanges)

Total per chain: 1 + N + M  (typically 4–7 calls/poll)
"""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.config import get_settings
from app.services.rate_limiter import etherscan_limiter
from app.services.transaction_service import transaction_service

logger = logging.getLogger(__name__)

ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
WEI = Decimal("1e18")

# chain_name -> config
CHAIN_CONFIGS: dict[str, dict] = {
    "ETH": {
        "chain_id": 1,
        "native_symbol": "ETH",
        "native_decimals": 18,
        "blocks_per_poll": 20,      # ~4 min at ~12s/block
        # (contract_address_lower, symbol, decimals)
        "tracked_tokens": [
            ("0xdac17f958d2ee523a2206206994597c13d831ec7", "USDT", 6),
            ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "USDC", 6),
            ("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", "WBTC", 8),
        ],
        # Known large exchange hot/cold wallets — queried for native ETH transfers
        "whale_addresses": [
            "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance 14
            "0x21a31ee1afc51d94c2efccaa2092ad1028285549",  # Binance 15
            "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8",  # Binance cold
            "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43",  # Coinbase cold
            "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",  # Coinbase 1
        ],
    },
    "BSC": {
        "chain_id": 56,
        "native_symbol": "BNB",
        "native_decimals": 18,
        "blocks_per_poll": 60,      # ~3 min at ~3s/block
        "tracked_tokens": [
            # BSC USDT and USDC use 18 decimals (different from ETH!)
            ("0x55d398326f99059ff775485246999027b3197955", "USDT", 18),
            ("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", "USDC", 18),
            ("0xe9e7cea3dedca5984780bafc599bd69add087d56", "BUSD", 18),
        ],
        "whale_addresses": [
            "0x8894e0a0c962cb723c1976a4421c95949be2d4e3",  # Binance BSC hot
            "0x161ba15a5f335c9f06bb5bbb0a9ce14076fbb645",  # Binance BSC 2
        ],
    },
    "MATIC": {
        "chain_id": 137,
        "native_symbol": "MATIC",
        "native_decimals": 18,
        "blocks_per_poll": 100,     # ~3 min at ~2s/block
        "tracked_tokens": [
            ("0xc2132d05d31c914a87c6611c10748aeb04b58e8f", "USDT", 6),
            ("0x2791bca1f2de4661ed88a30c99a7a9449aa84174", "USDC", 6),
        ],
        "whale_addresses": [
            "0xf977814e90da44bfa03b6295a0616a897441acec",  # Binance Polygon
        ],
    },
}


class EvmCollector(BaseCollector):
    """
    Unified EVM-chain whale collector via Etherscan API V2.
    Instantiate once per chain; all instances share the same rate limiter.
    """

    def __init__(self, chain_name: str):
        cfg = CHAIN_CONFIGS[chain_name]
        self.chain = chain_name
        self.native_symbol = cfg["native_symbol"]
        self._cfg = cfg
        self._settings = get_settings()

    @property
    def _api_key(self) -> str:
        return self._settings.etherscan_api_key

    @property
    def _chain_id(self) -> int:
        return self._cfg["chain_id"]

    # ──────────────────────────────────────────────────────────────
    # Main poll entry point
    # ──────────────────────────────────────────────────────────────

    async def poll(self, db: AsyncSession) -> None:
        self.log_poll_start()
        if not self._api_key:
            logger.warning("[%s] No ETHERSCAN_API_KEY set, skipping", self.chain)
            return

        last_block = await transaction_service.get_cursor(db, self.chain)

        try:
            latest_block = await self._get_latest_block()
            if latest_block <= last_block:
                return

            blocks_back = self._cfg["blocks_per_poll"]
            from_block = max(last_block + 1, latest_block - blocks_back)
            saved = 0

            # 1. ERC-20 token Transfer events (getLogs per tracked token)
            for contract_addr, symbol, decimals in self._cfg["tracked_tokens"]:
                logs = await self._get_token_logs(contract_addr, from_block, latest_block)
                for log in logs:
                    count = await self._process_token_log(db, log, symbol, decimals)
                    saved += count

            # 2. Native transfers from known whale/exchange addresses (txlist)
            for address in self._cfg["whale_addresses"]:
                txs = await self._get_txlist(address, from_block, latest_block)
                for tx in txs:
                    count = await self._process_native_tx(db, tx)
                    saved += count

            await transaction_service.update_cursor(db, self.chain, latest_block)
            self.log_poll_done(saved, -1)

        except Exception as exc:
            logger.error("[%s] Poll error: %s", self.chain, exc)
            await transaction_service.update_cursor(db, self.chain, last_block, error=str(exc))

    # ──────────────────────────────────────────────────────────────
    # ERC-20 log processing
    # ──────────────────────────────────────────────────────────────

    async def _process_token_log(
        self, db: AsyncSession, log: dict, symbol: str, decimals: int
    ) -> int:
        try:
            topics = log.get("topics", [])
            if len(topics) < 3:
                return 0
            if topics[0].lower() != TRANSFER_TOPIC:
                return 0

            from_addr = "0x" + topics[1][-40:]
            to_addr = "0x" + topics[2][-40:]
            data = log.get("data", "0x")
            if not data or data == "0x":
                return 0

            raw_amount = int(data, 16)
            amount = Decimal(raw_amount) / Decimal(10 ** decimals)

            block_number = int(log["blockNumber"], 16) if log.get("blockNumber") else None
            timestamp = int(log["timeStamp"], 16) if log.get("timeStamp") else 0
            block_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            tx_hash = log.get("transactionHash", "")

            ok = await transaction_service.save_if_whale(
                db,
                chain=self.chain,
                tx_hash=tx_hash,
                block_number=block_number,
                block_time=block_time,
                from_address=from_addr,
                to_address=to_addr,
                amount_native=amount,
                native_symbol=symbol,
                is_contract=False,
            )
            return 1 if ok else 0
        except Exception as exc:
            logger.debug("[%s] Log parse error: %s", self.chain, exc)
            return 0

    # ──────────────────────────────────────────────────────────────
    # Native tx processing
    # ──────────────────────────────────────────────────────────────

    async def _process_native_tx(self, db: AsyncSession, tx: dict) -> int:
        try:
            value_wei = int(tx.get("value", "0"))
            if value_wei == 0:
                return 0
            if tx.get("isError", "0") == "1":
                return 0

            decimals = self._cfg["native_decimals"]
            amount = Decimal(value_wei) / Decimal(10 ** decimals)
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
            return 1 if ok else 0
        except Exception as exc:
            logger.debug("[%s] Tx parse error: %s", self.chain, exc)
            return 0

    # ──────────────────────────────────────────────────────────────
    # Etherscan V2 API calls (all rate-limited + retried)
    # ──────────────────────────────────────────────────────────────

    async def _get_latest_block(self) -> int:
        data = await self._call(
            module="proxy",
            action="eth_blockNumber",
        )
        result = data.get("result", "0x0")
        return int(result, 16)

    async def _get_token_logs(
        self, contract_addr: str, from_block: int, to_block: int
    ) -> list[dict]:
        data = await self._call(
            module="logs",
            action="getLogs",
            address=contract_addr,
            fromBlock=str(from_block),
            toBlock=str(to_block),
            topic0=TRANSFER_TOPIC,
            offset="1000",
            page="1",
        )
        if data.get("status") == "1":
            return data.get("result", [])
        return []

    async def _get_txlist(
        self, address: str, from_block: int, to_block: int
    ) -> list[dict]:
        data = await self._call(
            module="account",
            action="txlist",
            address=address,
            startblock=str(from_block),
            endblock=str(to_block),
            sort="desc",
            offset="100",
            page="1",
        )
        if data.get("status") == "1":
            return data.get("result", [])
        return []

    async def _call(self, retries: int = 3, **params) -> dict:
        """
        Rate-limited, retried Etherscan V2 API call.
        - Waits for token bucket before each attempt.
        - Retries on HTTP 429 or Etherscan rate-limit message with exponential backoff.
        """
        base_params = {
            "chainid": str(self._chain_id),
            "apikey": self._api_key,
        }
        base_params.update(params)

        for attempt in range(retries):
            await etherscan_limiter.acquire()
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(ETHERSCAN_V2_URL, params=base_params)

                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("[%s] HTTP 429 — backing off %ds", self.chain, wait)
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Etherscan returns 200 with status="0" when rate-limited
                msg = data.get("result", "") or data.get("message", "")
                if isinstance(msg, str) and "rate limit" in msg.lower():
                    wait = 2 ** attempt
                    logger.warning("[%s] Etherscan rate limit msg — backing off %ds", self.chain, wait)
                    await asyncio.sleep(wait)
                    continue

                return data

            except httpx.TimeoutException:
                logger.warning("[%s] Request timeout (attempt %d/%d)", self.chain, attempt + 1, retries)
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except httpx.HTTPStatusError as exc:
                logger.warning("[%s] HTTP error %s", self.chain, exc.response.status_code)
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)

        logger.error("[%s] All %d retries failed for action=%s", self.chain, retries, params.get("action"))
        return {"status": "0", "result": []}
