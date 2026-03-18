from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/whalealert"

    # Etherscan API V2 — one key covers ETH (chainid=1), BSC (chainid=56), Polygon (chainid=137)
    # and 60+ other EVM chains. Get your free key at: https://etherscan.io/apis
    etherscan_api_key: str = ""

    # TronGrid (optional — works without key but rate limit is lower)
    trongrid_api_key: str = ""

    # CoinGecko (leave blank for free public endpoint; add Pro key for higher limits)
    coingecko_api_key: str = ""

    # App
    log_level: str = "INFO"
    port: int = 8000
    app_env: str = "production"

    # Whale thresholds in USD (override per chain via env var)
    whale_threshold_eth: int = 500_000
    whale_threshold_btc: int = 500_000
    whale_threshold_bsc: int = 200_000
    whale_threshold_sol: int = 200_000
    whale_threshold_trx: int = 100_000
    whale_threshold_matic: int = 100_000

    @property
    def whale_thresholds(self) -> dict[str, int]:
        return {
            "ETH": self.whale_threshold_eth,
            "BTC": self.whale_threshold_btc,
            "BSC": self.whale_threshold_bsc,
            "SOL": self.whale_threshold_sol,
            "TRX": self.whale_threshold_trx,
            "MATIC": self.whale_threshold_matic,
        }

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
