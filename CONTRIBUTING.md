# Contributing to Whale Alert

Thank you for your interest in contributing! Here's how to get started.

## Ways to Contribute

- **Add a new blockchain** — follow the pattern in `app/collectors/` to add support for a new chain
- **Improve exchange labels** — add known wallet addresses to `app/services/label_service.py`
- **Fix bugs** — open an issue first, then submit a PR
- **Improve docs** — README improvements, better code comments

## Development Setup

```bash
git clone https://github.com/quyendang/WhaleAlert.git
cd WhaleAlert
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in at least one blockchain API key in .env
docker-compose up -d db   # or run your own PostgreSQL
alembic upgrade head
uvicorn app.main:app --reload
```

## Adding a New Blockchain Collector

1. Create `app/collectors/newchain.py`:

```python
from app.collectors.base import BaseCollector
from sqlalchemy.ext.asyncio import AsyncSession

class NewChainCollector(BaseCollector):
    chain = "NEW"
    native_symbol = "TOKEN"

    async def poll(self, db: AsyncSession) -> None:
        # Fetch transactions, call transaction_service.save_if_whale()
        ...
```

2. Register in `app/collectors/__init__.py`
3. Add to `_collectors` and `_intervals` in `app/services/scheduler.py`
4. Add chain to `CHAINS` in `app/main.py` and `app/api/stats.py`
5. Add price mapping in `app/services/price_service.py`
6. Add threshold in `app/config.py`

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Run `pytest` before submitting
- Update `.env.example` if you add new env variables
- For new chains: include the free API source in PR description

## Reporting Issues

Please include:
- Your Python version
- Which blockchain(s) are affected
- Relevant log output (remove your API keys)
