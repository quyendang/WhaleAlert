from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/whalealert"

    # API Keys
    etherscan_api_key: str = ""
    bscscan_api_key: str = ""
    polygonscan_api_key: str = ""
    trongrid_api_key: str = ""
    coingecko_api_key: str = ""

    # App
    log_level: str = "INFO"
    port: int = 8000
    app_env: str = "production"

    # Whale thresholds in USD
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
