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
- `app/collectors/base.py` — abstract `BaseCollector` with `poll(db)` interface
- `app/services/transaction_service.py` — `save_if_whale()`: price lookup → threshold check → `INSERT ... ON CONFLICT DO NOTHING`
- `app/services/price_service.py` — CoinGecko TTL cache; stablecoins always return 1.0
- `app/services/scheduler.py` — APScheduler job registration; each chain has its own job and interval
- `app/models/transaction.py` — `WhaleTransaction` + `ChainCursor` SQLAlchemy models
- `app/api/transactions.py` — REST endpoints + SSE feed endpoint

### Adding a new blockchain

1. Create `app/collectors/newchain.py` extending `BaseCollector` with `chain`, `native_symbol` class attrs and `poll(db)` method
2. Add the collector to `app/collectors/__init__.py`
3. Add to `_collectors` and `_intervals` dicts in `app/services/scheduler.py`
4. Add chain to `CHAINS` list in `app/main.py` and `app/api/stats.py`
5. Add to `COINGECKO_IDS` in `app/services/price_service.py` if needed
6. Add whale threshold to `app/config.py`

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
