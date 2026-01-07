"""
Tests for PnL calculation functionality.

These tests validate the FIFO-based PnL calculation and fee handling.
All tests reflect the current behavior of the code.
"""

from decimal import Decimal

import pytest

from bot.tasks import _apply_trade_to_fifo, _fee_to_quote, _split_symbol


class TestSplitSymbol:
    """Tests for _split_symbol function."""

    def test_valid_symbol(self):
        """Test splitting a valid symbol like BTC/USDT."""
        base, quote = _split_symbol("BTC/USDT")
        assert base == "BTC"
        assert quote == "USDT"

    def test_valid_symbol_with_long_names(self):
        """Test splitting symbols with longer names."""
        base, quote = _split_symbol("DOGE/BUSD")
        assert base == "DOGE"
        assert quote == "BUSD"

    def test_invalid_symbol_no_slash(self):
        """Test that symbols without slash return None, None."""
        base, quote = _split_symbol("BTCUSDT")
        assert base is None
        assert quote is None

    def test_none_symbol(self):
        """Test that None symbol returns None, None."""
        base, quote = _split_symbol(None)
        assert base is None
        assert quote is None

    def test_empty_string_symbol(self):
        """Test that empty string returns None, None."""
        base, quote = _split_symbol("")
        assert base is None
        assert quote is None

    def test_symbol_with_multiple_slashes(self):
        """Test symbol with multiple slashes (edge case)."""
        base, quote = _split_symbol("BTC/USDT/EXTRA")
        assert base == "BTC"
        assert quote == "USDT/EXTRA"


class TestFeeToQuote:
    """Tests for _fee_to_quote function."""

    def test_fee_in_quote_unchanged(self):
        """Test that fee in quote currency is returned unchanged."""
        result = _fee_to_quote(
            fee_cost=Decimal("0.1"),
            fee_currency="USDT",
            price=Decimal("50000"),
            base_symbol="BTC",
            quote_symbol="USDT",
        )
        assert result == Decimal("0.1")

    def test_fee_in_base_converted(self):
        """Test that fee in base currency is converted using price."""
        # Fee of 0.001 BTC at price 50000 = 50 USDT
        result = _fee_to_quote(
            fee_cost=Decimal("0.001"),
            fee_currency="BTC",
            price=Decimal("50000"),
            base_symbol="BTC",
            quote_symbol="USDT",
        )
        assert result == Decimal("50")

    def test_fee_in_other_currency_returns_zero(self):
        """Test that fee in different currency (like BNB) returns 0."""
        result = _fee_to_quote(
            fee_cost=Decimal("0.01"),
            fee_currency="BNB",
            price=Decimal("50000"),
            base_symbol="BTC",
            quote_symbol="USDT",
        )
        assert result == Decimal("0")

    def test_none_fee_currency_returns_zero(self):
        """Test that None fee_currency returns 0."""
        result = _fee_to_quote(
            fee_cost=Decimal("0.1"),
            fee_currency=None,
            price=Decimal("50000"),
            base_symbol="BTC",
            quote_symbol="USDT",
        )
        assert result == Decimal("0")

    def test_none_base_symbol_returns_zero(self):
        """Test that None base_symbol returns 0."""
        result = _fee_to_quote(
            fee_cost=Decimal("0.1"),
            fee_currency="USDT",
            price=Decimal("50000"),
            base_symbol=None,
            quote_symbol="USDT",
        )
        assert result == Decimal("0")

    def test_none_quote_symbol_returns_zero(self):
        """Test that None quote_symbol returns 0."""
        result = _fee_to_quote(
            fee_cost=Decimal("0.1"),
            fee_currency="USDT",
            price=Decimal("50000"),
            base_symbol="BTC",
            quote_symbol=None,
        )
        assert result == Decimal("0")

    def test_zero_fee_cost(self):
        """Test that zero fee cost returns 0."""
        result = _fee_to_quote(
            fee_cost=Decimal("0"),
            fee_currency="USDT",
            price=Decimal("50000"),
            base_symbol="BTC",
            quote_symbol="USDT",
        )
        assert result == Decimal("0")


class TestApplyTradeToFifo:
    """Tests for _apply_trade_to_fifo function."""

    def test_buy_adds_to_lots(self):
        """Test that a buy trade adds a lot to the list."""
        buy_lots = []

        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="buy",
            price=Decimal("50000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        assert pnl == Decimal("0")
        assert len(buy_lots) == 1
        assert buy_lots[0]["price"] == Decimal("50000")
        assert buy_lots[0]["quantity"] == Decimal("1")

    def test_buy_includes_fee_in_effective_price(self):
        """Test that buy fee is included in effective price."""
        buy_lots = []

        # Buy 1 BTC at 50000 with 50 USDT fee
        # Effective price = 50000 + (50 / 1) = 50050
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="buy",
            price=Decimal("50000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("50"),
            fee_currency="USDT",
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        assert pnl == Decimal("0")
        assert len(buy_lots) == 1
        assert buy_lots[0]["price"] == Decimal("50050")
        assert buy_lots[0]["quantity"] == Decimal("1")

    def test_sell_removes_from_lots_fifo(self):
        """Test that sell consumes lots in FIFO order."""
        buy_lots = [
            {"price": Decimal("50000"), "quantity": Decimal("1")},
            {"price": Decimal("51000"), "quantity": Decimal("1")},
        ]

        # Sell 1 at 52000 - should use first lot at 50000
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("52000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL = (52000 - 50000) * 1 = 2000
        assert pnl == Decimal("2000")
        # First lot should be consumed
        assert len(buy_lots) == 1
        assert buy_lots[0]["price"] == Decimal("51000")

    def test_sell_partial_lot(self):
        """Test partial consumption of a lot."""
        buy_lots = [
            {"price": Decimal("50000"), "quantity": Decimal("2")},
        ]

        # Sell 1 of 2
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("51000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL = (51000 - 50000) * 1 = 1000
        assert pnl == Decimal("1000")
        # Lot should have 1 remaining
        assert len(buy_lots) == 1
        assert buy_lots[0]["quantity"] == Decimal("1")

    def test_sell_multiple_lots(self):
        """Test selling quantity that spans multiple lots."""
        buy_lots = [
            {"price": Decimal("50000"), "quantity": Decimal("1")},
            {"price": Decimal("51000"), "quantity": Decimal("1")},
        ]

        # Sell 1.5 - should consume first lot fully and half of second
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("52000"),
            quantity=Decimal("1.5"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL = (52000 - 50000) * 1 + (52000 - 51000) * 0.5 = 2000 + 500 = 2500
        assert pnl == Decimal("2500")
        # Second lot should have 0.5 remaining
        assert len(buy_lots) == 1
        assert buy_lots[0]["quantity"] == Decimal("0.5")

    def test_sell_without_buy_lots_returns_zero(self):
        """Test that selling without buy lots returns 0 PnL."""
        buy_lots = []

        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("52000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        assert pnl == Decimal("0")

    def test_fee_deducted_from_sell_pnl(self):
        """Test that fee is deducted from sell PnL."""
        buy_lots = [
            {"price": Decimal("50000"), "quantity": Decimal("1")},
        ]

        # Sell 1 at 52000 with 10 USDT fee
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("52000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("10"),
            fee_currency="USDT",
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL = (52000 - 50000) * 1 - 10 = 1990
        assert pnl == Decimal("1990")

    def test_sell_with_base_currency_fee(self):
        """Test sell with fee in base currency (BTC)."""
        buy_lots = [
            {"price": Decimal("50000"), "quantity": Decimal("1")},
        ]

        # Sell 1 at 52000 with 0.001 BTC fee (= 52 USDT at sell price)
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("52000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0.001"),
            fee_currency="BTC",
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL = (52000 - 50000) * 1 - (0.001 * 52000) = 2000 - 52 = 1948
        assert pnl == Decimal("1948")

    def test_sell_with_other_currency_fee_ignored(self):
        """Test that fee in other currency (BNB) is ignored."""
        buy_lots = [
            {"price": Decimal("50000"), "quantity": Decimal("1")},
        ]

        # Fee in BNB should be ignored (returns 0)
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("52000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0.1"),
            fee_currency="BNB",
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL = (52000 - 50000) * 1 = 2000 (fee ignored)
        assert pnl == Decimal("2000")

    def test_multiple_buys_then_sell(self):
        """Test realistic scenario: multiple buys followed by sell."""
        buy_lots = []

        # Buy 1 at 50000
        _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="buy",
            price=Decimal("50000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # Buy 1 at 48000 (price dropped)
        _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="buy",
            price=Decimal("48000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        assert len(buy_lots) == 2

        # Sell 1 at 51000 - should use first lot (FIFO)
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("51000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL = (51000 - 50000) * 1 = 1000
        assert pnl == Decimal("1000")
        # Should have one lot left at 48000
        assert len(buy_lots) == 1
        assert buy_lots[0]["price"] == Decimal("48000")

    def test_sell_more_than_available(self):
        """Test selling more quantity than available in lots."""
        buy_lots = [
            {"price": Decimal("50000"), "quantity": Decimal("1")},
        ]

        # Try to sell 2 when only 1 is available
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("52000"),
            quantity=Decimal("2"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL should be calculated only for available quantity
        # PnL = (52000 - 50000) * 1 = 2000
        assert pnl == Decimal("2000")
        # All lots consumed
        assert len(buy_lots) == 0

    def test_buy_with_zero_quantity_no_fee_division_error(self):
        """Test that zero quantity buy doesn't cause division by zero."""
        buy_lots = []

        # This should not raise an error
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="buy",
            price=Decimal("50000"),
            quantity=Decimal("0"),
            fee_cost=Decimal("10"),
            fee_currency="USDT",
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        assert pnl == Decimal("0")
        # Lot with 0 quantity still added (current behavior)
        assert len(buy_lots) == 1

    def test_loss_scenario(self):
        """Test a losing trade."""
        buy_lots = [
            {"price": Decimal("50000"), "quantity": Decimal("1")},
        ]

        # Sell at loss
        pnl = _apply_trade_to_fifo(
            buy_lots=buy_lots,
            side="sell",
            price=Decimal("48000"),
            quantity=Decimal("1"),
            fee_cost=Decimal("0"),
            fee_currency=None,
            base_symbol="BTC",
            quote_symbol="USDT",
        )

        # PnL = (48000 - 50000) * 1 = -2000
        assert pnl == Decimal("-2000")
