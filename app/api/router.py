from fastapi import APIRouter

from app.api import health, stats, transactions

router = APIRouter()

# Health check (no prefix)
router.include_router(health.router)

# API v1
api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(transactions.router)
api_v1.include_router(stats.router)

router.include_router(api_v1)
