# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (requires PostgreSQL)
uvicorn app.main:app --reload --port 8000

# Run with Docker (recommended for first run)
docker-compose up

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic current

# Tests
pytest
pytest tests/test_api/ -v
pytest tests/test_collectors/test_price_service.py -v

# Docker build
docker build -t whalealert .
```

## Architecture

Single-process FastAPI app combining HTTP server + background scheduler (APScheduler `AsyncIOScheduler`). **Must use `--workers 1`** — multiple workers would create duplicate schedulers and duplicate DB writes.

### Data flow

```
APScheduler jobs (every 10–60s)
  → Collector.poll(db)         [app/collectors/]
  → PriceService.get_usd_price()  [in-memory cache, refreshed every 60s]
  → TransactionService.save_if_whale()  [threshold check → upsert]
  → whale_transactions table

FastAPI routes
  → GET /api/v1/transactions    [paginated query]
  → GET /api/v1/transactions/feed  [SSE: polls DB every 3s, streams new rows]
  → GET /              [Jinja2 SSR + JS EventSource]
```

### Key files

- `app/main.py` — lifespan (runs migrations, inits cursors, starts scheduler), web UI routes, Jinja2 template filters
- `app/collectors/evm.py` — unified EVM collector using **Etherscan API V2** (`https://api.etherscan.io/v2/api`); handles ETH/BSC/MATIC via `chainid` parameter; all instances share `etherscan_limiter`
- `app/collectors/base.py` — abstract `BaseCollector` with `poll(db)` interface
- `app/services/rate_limiter.py` — `AsyncRateLimiter` token bucket; singleton `etherscan_limiter` (4 req/s) shared by all EVM collectors
- `app/services/transaction_service.py` — `save_if_whale()`: price lookup → threshold check → `INSERT ... ON CONFLICT DO NOTHING`
- `app/services/price_service.py` — CoinGecko TTL cache; stablecoins always return 1.0
- `app/services/scheduler.py` — APScheduler job registration with staggered start times (ETH+5s, BSC+15s, MATIC+25s) to prevent burst
- `app/models/transaction.py` — `WhaleTransaction` + `ChainCursor` SQLAlchemy models
- `app/api/transactions.py` — REST endpoints + SSE feed endpoint

### Etherscan API V2

- **Base URL**: `https://api.etherscan.io/v2/api`
- **Single key** for all EVM chains — set `ETHERSCAN_API_KEY` only
- **Chain IDs**: ETH=1, BSC=56, Polygon/MATIC=137
- **Rate limit**: 5 req/s, 100K calls/day (free tier)
- Rate limiter is set to **4 req/s** with burst=4 (buffer below the 5/s cap)
- Retry logic: 3 attempts with exponential backoff (1s → 2s → 4s) on HTTP 429 or Etherscan rate-limit message

### Data collection strategy (EVM)

Each chain per poll makes:
1. `proxy/eth_blockNumber` → 1 call (get current block)
2. `logs/getLogs` per tracked token → N calls (ERC-20 Transfer events in block range, filtered by `topic0=Transfer`)
3. `account/txlist` per whale address → M calls (native token transfers from known exchange wallets)

Estimated daily usage: ~43K calls (ETH ~17K + BSC ~14K + MATIC ~12K) — well within 100K free limit.

**BSC token decimals**: USDT and USDC on BSC use **18 decimals** (not 6 like on Ethereum). This is handled in `CHAIN_CONFIGS` in `evm.py`.

### Adding a new EVM chain (Etherscan V2 supported)

1. Add entry to `CHAIN_CONFIGS` in `app/collectors/evm.py` with `chain_id`, `native_symbol`, `tracked_tokens`, `whale_addresses`
2. Add chain to `CHAINS` list in `app/main.py` and `app/api/stats.py`
3. Add new poll job in `app/services/scheduler.py` with staggered `next_run_time`
4. Add threshold in `app/config.py` and `whale_thresholds` property
5. Add CoinGecko mapping in `app/services/price_service.py` if new native token

### Adding a non-EVM chain (BTC/SOL/TRX style)

1. Create `app/collectors/newchain.py` extending `BaseCollector`
2. Add to `app/collectors/__init__.py`
3. Add poll job in `app/services/scheduler.py`
4. Add chain to `CHAINS`, threshold to config, CoinGecko mapping

### Cursor-based incremental polling

Each collector reads `chain_cursors.last_block` before polling, scans from `last_block+1` to `latest_block`, then updates the cursor on success. On error, cursor is NOT updated — next poll retries from same block. This means a crash/restart has no data gaps.

### Dedup strategy

`INSERT ... ON CONFLICT ON CONSTRAINT uq_wt_hash_chain DO NOTHING` — safe to call multiple times with same `(tx_hash, chain)`. Collectors are written to be idempotent.

## Environment

See `.env.example` for all required variables. The only truly required ones are `DATABASE_URL` and at least one blockchain API key. BTC and SOL work without API keys.

## Koyeb deployment notes

- Use Docker builder, not buildpack
- Health check: `GET /health` on port 8000
- Link Koyeb managed PostgreSQL — it auto-injects `DATABASE_URL`
- Alembic migrations run automatically on app startup via `subprocess.run(["alembic", "upgrade", "head"])`
- `PORT` env var is injected by Koyeb automatically
