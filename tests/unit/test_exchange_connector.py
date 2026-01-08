"""Tests for CCXT connector sandbox handling."""

import types
from unittest.mock import MagicMock
import sys

import pytest

from bot.exchange.connector import CCXTConnector


class PermissionDenied(Exception):
    """Stub CCXT PermissionDenied."""


class AuthenticationError(Exception):
    """Stub CCXT AuthenticationError."""


def _build_fake_ccxt(created: dict) -> types.ModuleType:
    class DummyExchange:
        def __init__(self, options):
            self.options = options
            self.set_sandbox_mode = MagicMock()
            self.markets = {}
            created["exchange"] = self

        async def load_markets(self):
            self.markets = {"BTC/USDT": {}}

        async def fetch_balance(self):
            return {}

        async def close(self):
            return None

    fake_async = types.ModuleType("ccxt.async_support")
    fake_async.binance = DummyExchange
    fake_async.PermissionDenied = PermissionDenied
    fake_async.AuthenticationError = AuthenticationError

    fake_ccxt = types.ModuleType("ccxt")
    fake_ccxt.async_support = fake_async

    sys.modules["ccxt"] = fake_ccxt
    sys.modules["ccxt.async_support"] = fake_async

    return fake_async


@pytest.mark.asyncio
async def test_connect_enables_sandbox_mode_when_testnet():
    created: dict = {}
    _build_fake_ccxt(created)

    connector = CCXTConnector(
        exchange_id="binance",
        api_key="key",
        api_secret="secret",
        testnet=True,
    )

    await connector.connect()

    exchange = created["exchange"]
    exchange.set_sandbox_mode.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_validate_credentials_enables_sandbox_mode_when_testnet():
    created: dict = {}
    _build_fake_ccxt(created)

    connector = CCXTConnector(
        exchange_id="binance",
        api_key="key",
        api_secret="secret",
        testnet=True,
    )

    result = await connector.validate_credentials()

    exchange = created["exchange"]
    exchange.set_sandbox_mode.assert_called_once_with(True)
    assert result.is_valid is True
