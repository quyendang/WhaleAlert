from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chain: str
    tx_hash: str
    block_number: int | None
    block_time: datetime
    detected_at: datetime
    from_address: str | None
    to_address: str | None
    from_label: str | None
    to_label: str | None
    amount_native: Decimal
    native_symbol: str
    amount_usd: Decimal | None
    tx_type: str
    is_contract: bool


class TransactionDetail(TransactionResponse):
    usd_price_used: Decimal | None


class TransactionList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[TransactionResponse]
