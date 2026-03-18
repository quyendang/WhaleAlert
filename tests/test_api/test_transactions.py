"""API endpoint tests."""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_transactions_empty(client):
    resp = await client.get("/api/v1/transactions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_transactions_pagination(client):
    resp = await client.get("/api/v1/transactions?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_size"] == 10


@pytest.mark.asyncio
async def test_list_transactions_invalid_page_size(client):
    resp = await client.get("/api/v1/transactions?page_size=999")
    assert resp.status_code == 422  # validation error


@pytest.mark.asyncio
async def test_get_transaction_not_found(client):
    resp = await client.get("/api/v1/transactions/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stats_summary(client):
    resp = await client.get("/api/v1/stats/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_transactions_24h" in data
    assert "by_chain" in data


@pytest.mark.asyncio
async def test_stats_chains(client):
    resp = await client.get("/api/v1/stats/chains")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
