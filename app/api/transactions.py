"""Transaction API endpoints."""
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.transaction import WhaleTransaction
from app.schemas.transaction import TransactionDetail, TransactionList, TransactionResponse

router = APIRouter(prefix="/transactions", tags=["transactions"])

CHAINS = {"ETH", "BTC", "BSC", "SOL", "TRX", "MATIC"}


@router.get("", response_model=TransactionList)
async def list_transactions(
    chain: str | None = Query(None, description="Comma-separated chain filter, e.g. ETH,BTC"),
    min_usd: float | None = Query(None, ge=0),
    from_address: str | None = None,
    to_address: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str = Query("detected_at", pattern="^(detected_at|amount_usd)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WhaleTransaction)

    if chain:
        chains = [c.strip().upper() for c in chain.split(",") if c.strip().upper() in CHAINS]
        if chains:
            stmt = stmt.where(WhaleTransaction.chain.in_(chains))

    if min_usd is not None:
        stmt = stmt.where(WhaleTransaction.amount_usd >= min_usd)
    if from_address:
        stmt = stmt.where(WhaleTransaction.from_address == from_address.lower())
    if to_address:
        stmt = stmt.where(WhaleTransaction.to_address == to_address.lower())
    if from_time:
        stmt = stmt.where(WhaleTransaction.block_time >= from_time)
    if to_time:
        stmt = stmt.where(WhaleTransaction.block_time <= to_time)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Sort + paginate
    sort_col = WhaleTransaction.detected_at if sort == "detected_at" else WhaleTransaction.amount_usd
    sort_col = sort_col.desc() if order == "desc" else sort_col.asc()
    stmt = stmt.order_by(sort_col).offset((page - 1) * page_size).limit(page_size)

    rows = (await db.execute(stmt)).scalars().all()
    return TransactionList(
        total=total,
        page=page,
        page_size=page_size,
        items=[TransactionResponse.model_validate(r) for r in rows],
    )


@router.get("/feed")
async def transaction_feed(db: AsyncSession = Depends(get_db)):
    """Server-Sent Events stream of new whale transactions."""

    async def event_generator():
        last_id = 0
        # Get current max id as starting point
        result = await db.execute(text("SELECT COALESCE(MAX(id), 0) FROM whale_transactions"))
        last_id = result.scalar_one()

        while True:
            await asyncio.sleep(3)
            try:
                result = await db.execute(
                    select(WhaleTransaction)
                    .where(WhaleTransaction.id > last_id)
                    .order_by(WhaleTransaction.id.asc())
                    .limit(20)
                )
                rows = result.scalars().all()
                for row in rows:
                    last_id = row.id
                    data = TransactionResponse.model_validate(row).model_dump(mode="json")
                    yield f"data: {json.dumps(data)}\n\n"
            except Exception:
                yield "data: {\"error\": \"stream_error\"}\n\n"
                await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{tx_id}", response_model=TransactionDetail)
async def get_transaction(tx_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(WhaleTransaction, tx_id)
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionDetail.model_validate(row)
