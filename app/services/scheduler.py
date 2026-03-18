"""
APScheduler setup — all collectors + price refresh run inside FastAPI's event loop.

Poll interval design (Etherscan free tier: 5 req/s, 100K/day):
  Each EVM poll uses ~4–7 API calls. All 3 EVM chains share 1 Etherscan API key
  and therefore share the same rate limiter (etherscan_limiter).

  Calls/day estimate:
    ETH  (30s interval, ~6 calls/poll): 6 × 2880 = 17,280
    BSC  (30s interval, ~5 calls/poll): 5 × 2880 = 14,400
    MATIC(30s interval, ~4 calls/poll): 4 × 2880 = 11,520
    Total EVM: ~43,200 / day  ←  well within 100K

  Stagger start delays prevent all 3 chains from firing simultaneously,
  which would burst 15+ calls at once and hit the 5/s cap.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.collectors.btc import BtcCollector
from app.collectors.evm import EvmCollector
from app.collectors.sol import SolCollector
from app.collectors.trx import TrxCollector
from app.database import AsyncSessionLocal
from app.services.price_service import price_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    job_defaults={
        "misfire_grace_time": 30,
        "coalesce": True,       # skip accumulated misfires, run once
        "max_instances": 1,     # prevent job overlap if a poll runs long
    },
    timezone="UTC",
)

# ── Collector instances ────────────────────────────────────────────────────────
_evm_eth = EvmCollector("ETH")
_evm_bsc = EvmCollector("BSC")
_evm_matic = EvmCollector("MATIC")
_btc = BtcCollector()
_sol = SolCollector()
_trx = TrxCollector()


# ── Job wrappers ───────────────────────────────────────────────────────────────

async def _poll_eth():
    async with AsyncSessionLocal() as db:
        await _evm_eth.poll(db)


async def _poll_bsc():
    async with AsyncSessionLocal() as db:
        await _evm_bsc.poll(db)


async def _poll_matic():
    async with AsyncSessionLocal() as db:
        await _evm_matic.poll(db)


async def _poll_btc():
    async with AsyncSessionLocal() as db:
        await _btc.poll(db)


async def _poll_sol():
    async with AsyncSessionLocal() as db:
        await _sol.poll(db)


async def _poll_trx():
    async with AsyncSessionLocal() as db:
        await _trx.poll(db)


async def _refresh_prices():
    await price_service.refresh_prices()


# ── Setup ──────────────────────────────────────────────────────────────────────

def setup_scheduler() -> None:
    """
    Register all jobs with staggered start times.

    EVM chains (share Etherscan rate limit) start 10s apart so their polls
    never overlap in the first cycle. Non-EVM chains (BTC, SOL, TRX) use
    separate APIs and can start freely.
    """
    now = datetime.now(timezone.utc)

    # Price refresh — runs every 60s, starts immediately
    scheduler.add_job(
        _refresh_prices,
        "interval",
        seconds=60,
        id="price_refresh",
        next_run_time=now,
    )

    # EVM chains — staggered by 10s to spread API burst
    scheduler.add_job(_poll_eth,   "interval", seconds=30, id="poll_ETH",   next_run_time=now + timedelta(seconds=5))
    scheduler.add_job(_poll_bsc,   "interval", seconds=30, id="poll_BSC",   next_run_time=now + timedelta(seconds=15))
    scheduler.add_job(_poll_matic, "interval", seconds=30, id="poll_MATIC", next_run_time=now + timedelta(seconds=25))

    # Non-EVM chains — use separate APIs, no shared rate limit concern
    scheduler.add_job(_poll_btc, "interval", seconds=60, id="poll_BTC", next_run_time=now + timedelta(seconds=3))
    scheduler.add_job(_poll_sol, "interval", seconds=15, id="poll_SOL", next_run_time=now + timedelta(seconds=2))
    scheduler.add_job(_poll_trx, "interval", seconds=30, id="poll_TRX", next_run_time=now + timedelta(seconds=8))

    logger.info(
        "Scheduler configured: ETH/BSC/MATIC every 30s (staggered), BTC every 60s, SOL every 15s, TRX every 30s"
    )
