# 🐋 Whale Alert

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

Open-source real-time crypto whale transaction tracker. Monitors large transactions (≥ $100K–$500K USD) across **ETH, BTC, BSC, SOL, TRX, MATIC** blockchains and displays them on a live-updating website with a public REST API.

> Self-hosted alternative to [whale-alert.io](https://whale-alert.io/)

![screenshot placeholder](https://via.placeholder.com/800x400/0f0f1a/22c55e?text=Whale+Alert+Live+Feed)

## Features

- **Real-time feed** via Server-Sent Events — new whale transactions appear instantly without page refresh
- **6 blockchains**: Ethereum, Bitcoin, BNB Chain, Solana, TRON, Polygon
- **Exchange labeling**: identifies Binance, Coinbase, Kraken, OKX, Huobi and more
- **REST API** with filtering, pagination, and stats at `/api/v1/`
- **Interactive Swagger docs** at `/api/docs`
- **One-command deploy** to [Koyeb](https://koyeb.com) (free tier supported)
- **Zero-downtime restarts**: cursor-based polling ensures no transaction gaps

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/quyendang/WhaleAlert.git
cd WhaleAlert
cp .env.example .env
# Add at least one API key to .env (see table below)
docker-compose up
```

Open **http://localhost:8000**

### Manual

```bash
git clone https://github.com/quyendang/WhaleAlert.git
cd WhaleAlert
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # fill in DATABASE_URL and API keys
alembic upgrade head      # create database tables
uvicorn app.main:app --reload --port 8000
```

## API Keys

All API keys are **free**. The more keys you add, the more chains you'll see data from.

| Blockchain | Register at | Free Tier |
|-----------|-------------|-----------|
| **ETH** | [etherscan.io/apis](https://etherscan.io/apis) | 5 req/s, 100K calls/day |
| **BSC** | [bscscan.com/apis](https://bscscan.com/apis) | Same as Etherscan |
| **MATIC** | [polygonscan.com/apis](https://polygonscan.com/apis) | Same as Etherscan |
| **TRX** | [trongrid.io](https://www.trongrid.io/) | Optional (higher rate limit) |
| **BTC** | Blockstream.info | ✅ No key needed |
| **SOL** | Solana public RPC | ✅ No key needed |
| **Prices** | CoinGecko | ✅ No key needed |

## API Reference

Base URL: `http://localhost:8000/api/v1`

```
GET /transactions           # List whale transactions (paginated)
GET /transactions/{id}      # Single transaction detail
GET /transactions/feed      # Server-Sent Events live stream
GET /stats/summary          # 24h summary stats
GET /stats/chains           # Per-chain health and stats
GET /health                 # Health check
```

### Example request

```bash
# Latest 10 ETH whale transactions over $1M
curl "http://localhost:8000/api/v1/transactions?chain=ETH&min_usd=1000000&page_size=10"
```

```json
{
  "total": 42,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "id": 1,
      "chain": "ETH",
      "tx_hash": "0xabc...123",
      "block_time": "2026-03-18T12:34:56Z",
      "from_label": "Unknown",
      "to_label": "Binance",
      "amount_native": "2500.0",
      "native_symbol": "ETH",
      "amount_usd": "12500000.00",
      "tx_type": "exchange_deposit"
    }
  ]
}
```

Full docs available at **http://localhost:8000/api/docs**

## Deploy to Koyeb (Free)

1. Fork this repo
2. Create a [Koyeb](https://koyeb.com) account (free tier available)
3. New Service → GitHub → select your fork → **Docker** builder
4. Add environment variables from `.env.example`
5. Add **Koyeb managed PostgreSQL** add-on → link to service
6. Health check path: `/health`, port: `8000`
7. Deploy ✅

Migrations run automatically on every startup. No manual setup needed.

## Whale Thresholds

| Chain | Default | Override env var |
|-------|---------|------------------|
| ETH | $500,000 | `WHALE_THRESHOLD_ETH` |
| BTC | $500,000 | `WHALE_THRESHOLD_BTC` |
| BSC | $200,000 | `WHALE_THRESHOLD_BSC` |
| SOL | $200,000 | `WHALE_THRESHOLD_SOL` |
| TRX | $100,000 | `WHALE_THRESHOLD_TRX` |
| MATIC | $100,000 | `WHALE_THRESHOLD_MATIC` |

## Project Structure

```
app/
├── collectors/     # One file per blockchain (ETH, BTC, BSC, SOL, TRX, MATIC)
├── services/       # price_service, transaction_service, scheduler, label_service
├── api/            # FastAPI routes (transactions, stats, health)
├── models/         # SQLAlchemy ORM models
├── schemas/        # Pydantic response schemas
├── templates/      # Jinja2 HTML (base, index, transaction detail)
└── static/         # CSS + feed.js (SSE client)
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for how to:
- Add a new blockchain
- Add exchange wallet labels
- Report bugs

## License

[MIT](LICENSE) — free to use, modify, and deploy commercially.

---

*Built with FastAPI · SQLAlchemy · PostgreSQL · Tailwind CSS*
