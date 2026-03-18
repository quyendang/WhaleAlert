"""FastAPI application entry point."""
import logging
import subprocess
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text

from app.api.router import router
from app.config import get_settings
from app.database import AsyncSessionLocal, engine
from app.models.transaction import ChainCursor, WhaleTransaction
from app.services.price_service import price_service
from app.services.scheduler import scheduler, setup_scheduler

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")

CHAINS = ["ETH", "BTC", "BSC", "SOL", "TRX", "MATIC"]


# ─── Template filters ─────────────────────────────────────────────────────────

def format_usd(value) -> str:
    if value is None:
        return "—"
    n = float(value)
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{n/1e6:.2f}M"
    if n >= 1e3:
        return f"{n/1e3:.0f}K"
    return f"{n:.0f}"


def format_native(value) -> str:
    if value is None:
        return "—"
    n = float(value)
    if n >= 1e6:
        return f"{n/1e6:.2f}M"
    if n >= 1e3:
        return f"{n:,.2f}"
    return f"{n:,.4f}"


templates.env.filters["format_usd"] = format_usd
templates.env.filters["format_native"] = format_native


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Whale Alert...")

    # Run migrations
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True, capture_output=True)
        logger.info("Alembic migrations applied")
    except Exception as exc:
        logger.warning("Alembic migration failed (may be first run): %s", exc)

    # Initialize chain cursors
    async with AsyncSessionLocal() as db:
        for chain in CHAINS:
            await db.execute(
                text("""
                    INSERT INTO chain_cursors (chain, last_block, error_count)
                    VALUES (:chain, 0, 0)
                    ON CONFLICT (chain) DO NOTHING
                """),
                {"chain": chain},
            )
        await db.commit()
        logger.info("Chain cursors initialized")

    # Prime prices
    await price_service.refresh_prices()

    # Start scheduler
    setup_scheduler()
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    yield

    # Cleanup
    scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("Whale Alert stopped")


# ─── App factory ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Whale Alert API",
    description="Real-time crypto whale transaction tracker",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)


# ─── Web UI routes ────────────────────────────────────────────────────────────

@app.get("/")
async def index(
    request: Request,
    page: int = 1,
    page_size: int = 25,
    chain: str | None = None,
    min_usd: float | None = None,
    sort: str = "detected_at",
):
    async with AsyncSessionLocal() as db:
        stmt = select(WhaleTransaction)
        if chain:
            stmt = stmt.where(WhaleTransaction.chain == chain.upper())
        if min_usd:
            stmt = stmt.where(WhaleTransaction.amount_usd >= min_usd)

        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar_one()

        sort_col = WhaleTransaction.detected_at if sort == "detected_at" else WhaleTransaction.amount_usd
        stmt = stmt.order_by(sort_col.desc()).offset((page - 1) * page_size).limit(page_size)
        transactions = (await db.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "transactions": transactions,
            "total": total,
            "page": page,
            "page_size": page_size,
            "active_chain": chain,
        },
    )


@app.get("/chain/{chain_name}")
async def chain_view(request: Request, chain_name: str):
    return await index(request, chain=chain_name.upper())


@app.get("/tx/{tx_id}")
async def transaction_detail(request: Request, tx_id: int):
    async with AsyncSessionLocal() as db:
        tx = await db.get(WhaleTransaction, tx_id)
    if not tx:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Transaction not found")
    return templates.TemplateResponse("transaction_detail.html", {"request": request, "tx": tx})
