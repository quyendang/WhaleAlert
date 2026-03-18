"""Price service tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.price_service import PriceService


@pytest.mark.asyncio
async def test_stable_coins_return_1():
    svc = PriceService()
    assert svc.get_usd_price("USDT") == 1.0
    assert svc.get_usd_price("USDC") == 1.0
    assert svc.get_usd_price("DAI") == 1.0


@pytest.mark.asyncio
async def test_unknown_symbol_returns_none():
    svc = PriceService()
    assert svc.get_usd_price("UNKNOWN_TOKEN_XYZ") is None


@pytest.mark.asyncio
async def test_price_cached_after_refresh():
    svc = PriceService()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ethereum": {"usd": 3500.0},
        "bitcoin": {"usd": 65000.0},
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        await svc.refresh_prices()

    assert svc.get_usd_price("ETH") == 3500.0
    assert svc.get_usd_price("BTC") == 65000.0


def test_label_service():
    from app.services.label_service import get_label
    assert get_label("0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be") == "Binance"
    assert get_label("0xunknownaddress123") == "Unknown"
    assert get_label("") == "Unknown"
