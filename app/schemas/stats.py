from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ChainStats(BaseModel):
    chain: str
    count: int
    total_usd: Decimal | None
    last_block: int
    last_polled_at: datetime | None
    error_count: int


class StatsSummary(BaseModel):
    total_transactions_24h: int
    total_usd_24h: Decimal | None
    by_chain: dict[str, ChainStats]
    largest_24h: dict | None
