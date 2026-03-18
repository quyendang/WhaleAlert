"""APScheduler setup — runs all collectors + price refresh inside FastAPI's event loop."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.collectors import BscCollector, BtcCollector, EthCollector, MaticCollector, SolCollector, TrxCollector
from app.database import AsyncSessionLocal
from app.services.price_service import price_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    job_defaults={
        "misfire_grace_time": 30,
        "coalesce": True,
        "max_instances": 1,
    },
    timezone="UTC",
)

# Collector instances
_collectors = {
    "ETH": EthCollector(),
    "BSC": BscCollector(),
    "MATIC": MaticCollector(),
    "BTC": BtcCollector(),
    "SOL": SolCollector(),
    "TRX": TrxCollector(),
}

# Poll intervals in seconds
_intervals = {
    "ETH": 15,
    "BSC": 15,
    "MATIC": 20,
    "BTC": 60,
    "SOL": 10,
    "TRX": 30,
}


async def _poll_chain(chain: str) -> None:
    collector = _collectors[chain]
    async with AsyncSessionLocal() as db:
        await collector.poll(db)


async def _refresh_prices() -> None:
    await price_service.refresh_prices()


def setup_scheduler() -> None:
    """Register all jobs. Call once during app startup."""
    # Price refresh — every 60 seconds
    scheduler.add_job(
        _refresh_prices,
        "interval",
        seconds=60,
        id="price_refresh",
        next_run_time=None,  # run immediately on first tick
    )

    # Blockchain collectors
    for chain, interval in _intervals.items():
        scheduler.add_job(
            _poll_chain,
            "interval",
            seconds=interval,
            id=f"poll_{chain}",
            args=[chain],
        )

    logger.info("Scheduler configured with %d jobs", len(scheduler.get_jobs()))
