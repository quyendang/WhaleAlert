"""Stats API endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.transaction import ChainCursor, WhaleTransaction
from app.schemas.stats import ChainStats, StatsSummary
from app.schemas.transaction import TransactionResponse

router = APIRouter(prefix="/stats", tags=["stats"])

CHAINS = ["ETH", "BTC", "BSC", "SOL", "TRX", "MATIC"]


@router.get("/summary", response_model=StatsSummary)
async def get_summary(db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Total count & volume 24h
    result = await db.execute(
        select(
            func.count().label("total"),
            func.sum(WhaleTransaction.amount_usd).label("total_usd"),
        ).where(WhaleTransaction.detected_at >= since)
    )
    row = result.one()
    total_24h = row.total or 0
    total_usd_24h = row.total_usd

    # Per-chain breakdown
    chain_rows = await db.execute(
        select(
            WhaleTransaction.chain,
            func.count().label("count"),
            func.sum(WhaleTransaction.amount_usd).label("total_usd"),
        )
        .where(WhaleTransaction.detected_at >= since)
        .group_by(WhaleTransaction.chain)
    )
    by_chain_data = {r.chain: {"count": r.count, "total_usd": r.total_usd} for r in chain_rows}

    # Cursors
    cursors = (await db.execute(select(ChainCursor))).scalars().all()
    cursor_map = {c.chain: c for c in cursors}

    by_chain = {}
    for chain in CHAINS:
        cursor = cursor_map.get(chain)
        data = by_chain_data.get(chain, {"count": 0, "total_usd": None})
        by_chain[chain] = ChainStats(
            chain=chain,
            count=data["count"],
            total_usd=data["total_usd"],
            last_block=cursor.last_block if cursor else 0,
            last_polled_at=cursor.last_polled_at if cursor else None,
            error_count=cursor.error_count if cursor else 0,
        )

    # Largest 24h transaction
    largest_row = await db.execute(
        select(WhaleTransaction)
        .where(WhaleTransaction.detected_at >= since)
        .order_by(WhaleTransaction.amount_usd.desc().nullslast())
        .limit(1)
    )
    largest = largest_row.scalars().first()
    largest_dict = TransactionResponse.model_validate(largest).model_dump(mode="json") if largest else None

    return StatsSummary(
        total_transactions_24h=total_24h,
        total_usd_24h=total_usd_24h,
        by_chain=by_chain,
        largest_24h=largest_dict,
    )


@router.get("/chains", response_model=list[ChainStats])
async def get_chain_stats(db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    cursors = (await db.execute(select(ChainCursor))).scalars().all()
    cursor_map = {c.chain: c for c in cursors}

    chain_rows = await db.execute(
        select(
            WhaleTransaction.chain,
            func.count().label("count"),
            func.sum(WhaleTransaction.amount_usd).label("total_usd"),
        )
        .where(WhaleTransaction.detected_at >= since)
        .group_by(WhaleTransaction.chain)
    )
    by_chain_data = {r.chain: {"count": r.count, "total_usd": r.total_usd} for r in chain_rows}

    result = []
    for chain in CHAINS:
        cursor = cursor_map.get(chain)
        data = by_chain_data.get(chain, {"count": 0, "total_usd": None})
        result.append(ChainStats(
            chain=chain,
            count=data["count"],
            total_usd=data["total_usd"],
            last_block=cursor.last_block if cursor else 0,
            last_polled_at=cursor.last_polled_at if cursor else None,
            error_count=cursor.error_count if cursor else 0,
        ))
    return result
