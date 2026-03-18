"""CoinGecko price service with in-memory TTL cache."""
import logging
import time
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

COINGECKO_IDS = {
    "ETH": "ethereum",
    "BTC": "bitcoin",
    "BNB": "binancecoin",
    "SOL": "solana",
    "TRX": "tron",
    "MATIC": "matic-network",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BUSD": "binance-usd",
    "DAI": "dai",
}

PRICE_TTL = 60  # seconds


class PriceService:
    def __init__(self):
        self._cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, timestamp)
        self._settings = get_settings()

    def get_usd_price(self, symbol: str) -> Optional[float]:
        """Return cached USD price for symbol. Returns None if never fetched."""
        symbol = symbol.upper()
        if symbol in ("USDT", "USDC", "BUSD", "DAI"):
            return 1.0
        entry = self._cache.get(symbol)
        if entry:
            return entry[0]
        return None

    async def refresh_prices(self) -> None:
        """Fetch latest prices from CoinGecko for all tracked symbols."""
        ids = ",".join(COINGECKO_IDS.values())
        base_url = "https://api.coingecko.com/api/v3"
        headers = {}
        if self._settings.coingecko_api_key:
            headers["x-cg-pro-api-key"] = self._settings.coingecko_api_key
            base_url = "https://pro-api.coingecko.com/api/v3"

        url = f"{base_url}/simple/price?ids={ids}&vs_currencies=usd"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            now = time.time()
            for symbol, cg_id in COINGECKO_IDS.items():
                price = data.get(cg_id, {}).get("usd")
                if price is not None:
                    self._cache[symbol] = (float(price), now)
            logger.debug("Prices refreshed: %s", {k: v[0] for k, v in self._cache.items()})
        except Exception as exc:
            logger.warning("Price refresh failed: %s (using cached values)", exc)


# Singleton
price_service = PriceService()
