"""
Unit Tests for Order Manager.

Tests for order state machine transitions and order lifecycle.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bot.order_manager import (
    ManagedOrder,
    OrderManager,
    OrderState,
    OrderTransitionError,
    ORDER_TRANSITIONS,
)


class TestOrderState:
    """Tests for OrderState enum and transitions."""

    def test_all_states_defined(self) -> None:
        """All expected states should be defined."""
        expected_states = [
            "PENDING",
            "SUBMITTING",
            "OPEN",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELLING",
            "CANCELLED",
            "REJECTED",
            "ERROR",
        ]
        actual_states = [s.name for s in OrderState]
        assert sorted(actual_states) == sorted(expected_states)

    def test_terminal_states_have_no_transitions(self) -> None:
        """Terminal states should not allow any transitions."""
        terminal_states = [
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.ERROR,
        ]
        for state in terminal_states:
            assert ORDER_TRANSITIONS[state] == [], f"{state} should have no transitions"

    def test_pending_can_transition_to_submitting(self) -> None:
        """PENDING should be able to transition to SUBMITTING."""
        assert OrderState.SUBMITTING in ORDER_TRANSITIONS[OrderState.PENDING]

    def test_pending_can_transition_to_cancelled(self) -> None:
        """PENDING should be able to transition to CANCELLED (cancel before submit)."""
        assert OrderState.CANCELLED in ORDER_TRANSITIONS[OrderState.PENDING]

    def test_submitting_can_transition_to_open(self) -> None:
        """SUBMITTING should be able to transition to OPEN."""
        assert OrderState.OPEN in ORDER_TRANSITIONS[OrderState.SUBMITTING]

    def test_submitting_can_transition_to_rejected(self) -> None:
        """SUBMITTING should be able to transition to REJECTED."""
        assert OrderState.REJECTED in ORDER_TRANSITIONS[OrderState.SUBMITTING]

    def test_submitting_can_transition_to_error(self) -> None:
        """SUBMITTING should be able to transition to ERROR."""
        assert OrderState.ERROR in ORDER_TRANSITIONS[OrderState.SUBMITTING]

    def test_open_can_transition_to_partially_filled(self) -> None:
        """OPEN should be able to transition to PARTIALLY_FILLED."""
        assert OrderState.PARTIALLY_FILLED in ORDER_TRANSITIONS[OrderState.OPEN]

    def test_open_can_transition_to_filled(self) -> None:
        """OPEN should be able to transition to FILLED."""
        assert OrderState.FILLED in ORDER_TRANSITIONS[OrderState.OPEN]

    def test_open_can_transition_to_cancelling(self) -> None:
        """OPEN should be able to transition to CANCELLING."""
        assert OrderState.CANCELLING in ORDER_TRANSITIONS[OrderState.OPEN]

    def test_partially_filled_can_transition_to_filled(self) -> None:
        """PARTIALLY_FILLED should be able to transition to FILLED."""
        assert OrderState.FILLED in ORDER_TRANSITIONS[OrderState.PARTIALLY_FILLED]

    def test_cancelling_can_transition_to_cancelled(self) -> None:
        """CANCELLING should be able to transition to CANCELLED."""
        assert OrderState.CANCELLED in ORDER_TRANSITIONS[OrderState.CANCELLING]

    def test_cancelling_can_transition_to_filled(self) -> None:
        """CANCELLING can transition to FILLED (if filled before cancel processed)."""
        assert OrderState.FILLED in ORDER_TRANSITIONS[OrderState.CANCELLING]


class TestManagedOrder:
    """Tests for ManagedOrder dataclass."""

    @pytest.fixture
    def sample_order(self) -> ManagedOrder:
        """Create a sample managed order."""
        return ManagedOrder(
            bot_id=uuid4(),
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
        )

    def test_default_state_is_pending(self, sample_order: ManagedOrder) -> None:
        """New orders should start in PENDING state."""
        assert sample_order.state == OrderState.PENDING

    def test_default_filled_quantity_is_zero(self, sample_order: ManagedOrder) -> None:
        """New orders should have zero filled quantity."""
        assert sample_order.filled_quantity == Decimal("0")

    def test_is_terminal_false_for_pending(self, sample_order: ManagedOrder) -> None:
        """PENDING should not be terminal."""
        assert sample_order.is_terminal is False

    def test_is_terminal_true_for_filled(self, sample_order: ManagedOrder) -> None:
        """FILLED should be terminal."""
        sample_order.state = OrderState.FILLED
        assert sample_order.is_terminal is True

    def test_is_terminal_true_for_cancelled(self, sample_order: ManagedOrder) -> None:
        """CANCELLED should be terminal."""
        sample_order.state = OrderState.CANCELLED
        assert sample_order.is_terminal is True

    def test_is_terminal_true_for_rejected(self, sample_order: ManagedOrder) -> None:
        """REJECTED should be terminal."""
        sample_order.state = OrderState.REJECTED
        assert sample_order.is_terminal is True

    def test_is_terminal_true_for_error(self, sample_order: ManagedOrder) -> None:
        """ERROR should be terminal."""
        sample_order.state = OrderState.ERROR
        assert sample_order.is_terminal is True

    def test_is_active_false_for_pending(self, sample_order: ManagedOrder) -> None:
        """PENDING should not be active."""
        assert sample_order.is_active is False

    def test_is_active_true_for_open(self, sample_order: ManagedOrder) -> None:
        """OPEN should be active."""
        sample_order.state = OrderState.OPEN
        assert sample_order.is_active is True

    def test_is_active_true_for_partially_filled(
        self, sample_order: ManagedOrder
    ) -> None:
        """PARTIALLY_FILLED should be active."""
        sample_order.state = OrderState.PARTIALLY_FILLED
        assert sample_order.is_active is True

    def test_remaining_quantity(self, sample_order: ManagedOrder) -> None:
        """Remaining quantity should be calculated correctly."""
        sample_order.filled_quantity = Decimal("0.03")
        assert sample_order.remaining_quantity == Decimal("0.07")

    def test_fill_percent(self, sample_order: ManagedOrder) -> None:
        """Fill percent should be calculated correctly."""
        sample_order.filled_quantity = Decimal("0.05")
        assert sample_order.fill_percent == Decimal("50")

    def test_fill_percent_zero_quantity(self) -> None:
        """Fill percent should handle zero quantity."""
        order = ManagedOrder(
            bot_id=uuid4(),
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0"),
        )
        assert order.fill_percent == Decimal("0")

    def test_can_transition_to_valid_state(self, sample_order: ManagedOrder) -> None:
        """Should allow valid transitions."""
        assert sample_order.can_transition_to(OrderState.SUBMITTING) is True

    def test_can_transition_to_invalid_state(self, sample_order: ManagedOrder) -> None:
        """Should reject invalid transitions."""
        assert sample_order.can_transition_to(OrderState.FILLED) is False

    def test_can_transition_from_terminal_state(
        self, sample_order: ManagedOrder
    ) -> None:
        """Terminal states should not allow any transitions."""
        sample_order.state = OrderState.FILLED
        assert sample_order.can_transition_to(OrderState.OPEN) is False
        assert sample_order.can_transition_to(OrderState.CANCELLED) is False


class TestOrderTransitionError:
    """Tests for OrderTransitionError exception."""

    def test_error_message(self) -> None:
        """Error should have informative message."""
        error = OrderTransitionError(OrderState.PENDING, OrderState.FILLED)
        assert "pending" in str(error)
        assert "filled" in str(error)

    def test_error_attributes(self) -> None:
        """Error should store state information."""
        error = OrderTransitionError(OrderState.OPEN, OrderState.PENDING)
        assert error.current_state == OrderState.OPEN
        assert error.target_state == OrderState.PENDING


@pytest.mark.asyncio
class TestOrderManager:
    """Tests for OrderManager class."""

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create a mock exchange connector."""
        mock = MagicMock()
        mock.create_order = AsyncMock(
            return_value={
                "id": "exchange-order-123",
                "status": "open",
            }
        )
        mock.cancel_order = AsyncMock(return_value=True)
        mock.fetch_order = AsyncMock(
            return_value={
                "id": "exchange-order-123",
                "status": "open",
                "filled": 0,
            }
        )
        return mock

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create a mock database session."""
        mock = MagicMock()
        mock.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
        mock.add = MagicMock()
        mock.commit = AsyncMock()
        mock.rollback = AsyncMock()
        return mock

    @pytest.fixture
    def order_manager(
        self, mock_exchange: MagicMock, mock_db_session: MagicMock
    ) -> OrderManager:
        """Create an OrderManager instance."""
        return OrderManager(
            exchange=mock_exchange,
            db_session=mock_db_session,
            base_retry_delay=0.01,  # Fast retries for tests
            max_retry_delay=0.05,
        )

    @pytest.fixture
    def sample_order(self) -> ManagedOrder:
        """Create a sample order."""
        return ManagedOrder(
            bot_id=uuid4(),
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
        )

    async def test_submit_order_success(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Order should be submitted successfully."""
        result = await order_manager.submit_order(sample_order)

        assert result.state == OrderState.OPEN
        assert result.exchange_id == "exchange-order-123"
        assert result.submitted_at is not None

    async def test_submit_order_transitions_through_submitting(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Order should transition through SUBMITTING state."""
        # We can verify by checking the exchange was called
        await order_manager.submit_order(sample_order)

        order_manager.exchange.create_order.assert_called_once_with(
            symbol="BTC/USDT",
            order_type="limit",
            side="buy",
            amount=0.1,
            price=50000.0,
        )

    async def test_submit_order_from_invalid_state(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Submit from invalid state should raise error."""
        sample_order.state = OrderState.FILLED

        with pytest.raises(OrderTransitionError) as exc_info:
            await order_manager.submit_order(sample_order)

        assert exc_info.value.current_state == OrderState.FILLED
        assert exc_info.value.target_state == OrderState.SUBMITTING

    async def test_submit_order_with_exchange_error(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Exchange error should transition to ERROR state."""
        sample_order.max_retries = 0  # No retries
        order_manager.exchange.create_order = AsyncMock(
            side_effect=Exception("Exchange error")
        )

        with pytest.raises(Exception, match="Exchange error"):
            await order_manager.submit_order(sample_order)

        assert sample_order.state == OrderState.ERROR
        assert sample_order.last_error == "Exchange error"

    async def test_submit_order_retry_on_failure(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Order submission should retry on failure."""
        # Fail twice, then succeed
        order_manager.exchange.create_order = AsyncMock(
            side_effect=[
                Exception("Temporary error"),
                Exception("Temporary error"),
                {"id": "order-123", "status": "open"},
            ]
        )
        sample_order.max_retries = 3

        result = await order_manager.submit_order(sample_order)

        assert result.state == OrderState.OPEN
        assert result.retry_count == 2
        assert order_manager.exchange.create_order.call_count == 3

    async def test_cancel_order_success(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Open order should be cancelled successfully."""
        # First submit the order
        await order_manager.submit_order(sample_order)

        # Then cancel
        result = await order_manager.cancel_order(sample_order.id)

        assert result is True
        assert sample_order.state == OrderState.CANCELLED

    async def test_cancel_order_not_found(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Cancelling unknown order should return False."""
        result = await order_manager.cancel_order(uuid4())
        assert result is False

    async def test_cancel_order_from_pending(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Cannot cancel PENDING order that's not in manager."""
        result = await order_manager.cancel_order(sample_order.id)
        assert result is False

    async def test_get_open_orders(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Should return only active orders."""
        await order_manager.submit_order(sample_order)

        orders = await order_manager.get_open_orders()

        assert len(orders) == 1
        assert orders[0].id == sample_order.id

    async def test_get_open_orders_by_bot(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Should filter orders by bot_id."""
        bot_id_1 = uuid4()
        bot_id_2 = uuid4()

        order_1 = ManagedOrder(
            bot_id=bot_id_1,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
        )
        order_2 = ManagedOrder(
            bot_id=bot_id_2,
            symbol="ETH/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("1"),
            price=Decimal("3000"),
        )

        await order_manager.submit_order(order_1)
        await order_manager.submit_order(order_2)

        orders = await order_manager.get_open_orders(bot_id=bot_id_1)

        assert len(orders) == 1
        assert orders[0].bot_id == bot_id_1

    async def test_cancel_all_orders(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Should cancel all active orders for a bot."""
        bot_id = uuid4()

        order_1 = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
        )
        order_2 = ManagedOrder(
            bot_id=bot_id,
            symbol="ETH/USDT",
            side="sell",
            order_type="limit",
            quantity=Decimal("1"),
            price=Decimal("3500"),
        )

        await order_manager.submit_order(order_1)
        await order_manager.submit_order(order_2)

        cancelled = await order_manager.cancel_all_orders(bot_id)

        assert cancelled == 2
        assert order_1.state == OrderState.CANCELLED
        assert order_2.state == OrderState.CANCELLED

    async def test_handle_websocket_update_fill(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """WebSocket update should update order state."""
        filled_callback = MagicMock()
        order_manager.on_order_filled = filled_callback

        await order_manager.submit_order(sample_order)

        # Simulate WebSocket fill update
        await order_manager.handle_websocket_update({
            "orderId": "exchange-order-123",
            "status": "filled",
            "filled": 0.1,
            "average": 50100.0,
        })

        assert sample_order.state == OrderState.FILLED
        assert sample_order.filled_quantity == Decimal("0.1")
        assert sample_order.average_fill_price == Decimal("50100.0")
        filled_callback.assert_called_once_with(sample_order)

    async def test_handle_websocket_update_partial_fill(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Partial fill should transition to PARTIALLY_FILLED."""
        await order_manager.submit_order(sample_order)

        await order_manager.handle_websocket_update({
            "orderId": "exchange-order-123",
            "status": "open",
            "filled": 0.05,
            "average": 50000.0,
        })

        assert sample_order.state == OrderState.PARTIALLY_FILLED
        assert sample_order.filled_quantity == Decimal("0.05")

    async def test_handle_websocket_update_unknown_order(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Unknown order ID should be ignored."""
        # Should not raise
        await order_manager.handle_websocket_update({
            "orderId": "unknown-order-id",
            "status": "filled",
        })

    async def test_sync_order_status(
        self,
        order_manager: OrderManager,
        sample_order: ManagedOrder,
    ) -> None:
        """Should sync order status from exchange."""
        order_manager.exchange.fetch_order = AsyncMock(
            return_value={
                "id": "exchange-order-123",
                "status": "closed",
                "filled": 0.1,
                "average": 50050.0,
            }
        )

        await order_manager.submit_order(sample_order)
        result = await order_manager.sync_order_status(sample_order.id)

        assert result is not None
        assert result.state == OrderState.FILLED
        assert result.filled_quantity == Decimal("0.1")

    async def test_get_orders_by_bot_with_state_filter(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Should filter orders by state."""
        bot_id = uuid4()

        order_1 = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
        )
        order_2 = ManagedOrder(
            bot_id=bot_id,
            symbol="ETH/USDT",
            side="sell",
            order_type="limit",
            quantity=Decimal("1"),
            price=Decimal("3500"),
        )

        await order_manager.submit_order(order_1)
        await order_manager.submit_order(order_2)

        # Cancel one order
        await order_manager.cancel_order(order_1.id)

        # Get only OPEN orders
        open_orders = await order_manager.get_orders_by_bot(
            bot_id, states=[OrderState.OPEN]
        )
        assert len(open_orders) == 1
        assert open_orders[0].id == order_2.id

        # Get only CANCELLED orders
        cancelled_orders = await order_manager.get_orders_by_bot(
            bot_id, states=[OrderState.CANCELLED]
        )
        assert len(cancelled_orders) == 1
        assert cancelled_orders[0].id == order_1.id
