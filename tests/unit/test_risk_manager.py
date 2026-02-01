"""
Comprehensive Unit Tests for Risk Manager.

Tests for the risk management engine covering:
- Evaluate risk returns OK when within limits
- Daily/weekly/monthly stop triggers
- Trailing stop activation and recovery
- Risk cooldown periods
- State transitions and persistence
- Reinforcements
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import RiskState
from bot.risk_manager import (
    RiskAction,
    RiskConfig,
    RiskDecision,
    RiskManager,
    RiskStatus,
)


class TestRiskConfig:
    """Tests for RiskConfig defaults and validation."""

    def test_risk_config_defaults(self) -> None:
        """Config should have sensible defaults when settings are used."""
        config = RiskConfig(
            daily_stop_percent=Decimal("4"),
            weekly_stop_percent=Decimal("10"),
            monthly_stop_percent=Decimal("20"),
            daily_pause_hours=24,
            two_step_wait_minutes=30,
            trailing_percent=Decimal("3"),
            trailing_wait_minutes=30,
            active_capital_percent=Decimal("60"),
            reserve_capital_percent=Decimal("40"),
            reinforcement_levels_percent=[Decimal("8"), Decimal("15")],
        )

        assert config.daily_stop_percent == Decimal("4")
        assert config.weekly_stop_percent == Decimal("10")
        assert config.monthly_stop_percent == Decimal("20")
        assert config.daily_pause_hours == 24
        assert config.two_step_wait_minutes == 30
        assert config.trailing_percent == Decimal("3")
        assert len(config.reinforcement_levels_percent) == 2


class TestRiskStatus:
    """Tests for RiskStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """All expected statuses should be defined."""
        expected = ["OK", "PAUSED", "PENDING_LIQUIDATION", "LIQUIDATED"]
        actual = [s.name for s in RiskStatus]
        assert sorted(actual) == sorted(expected)


class TestRiskAction:
    """Tests for RiskAction enum."""

    def test_all_actions_defined(self) -> None:
        """All expected actions should be defined."""
        expected = [
            "NONE",
            "PAUSE",
            "PENDING_LIQUIDATION",
            "LIQUIDATE",
            "RESUME",
        ]
        actual = [a.name for a in RiskAction]
        assert sorted(actual) == sorted(expected)


class TestRiskDecision:
    """Tests for RiskDecision dataclass."""

    def test_decision_with_defaults(self) -> None:
        """Decision should have optional fields."""
        decision = RiskDecision(status=RiskStatus.OK, action=RiskAction.NONE)
        assert decision.status == RiskStatus.OK
        assert decision.action == RiskAction.NONE
        assert decision.reason is None
        assert decision.metadata is None

    def test_decision_with_all_fields(self) -> None:
        """Decision should accept all fields."""
        decision = RiskDecision(
            status=RiskStatus.PAUSED,
            action=RiskAction.PAUSE,
            reason="daily_stop",
            metadata={"equity": "9500"},
        )
        assert decision.status == RiskStatus.PAUSED
        assert decision.action == RiskAction.PAUSE
        assert decision.reason == "daily_stop"
        assert decision.metadata == {"equity": "9500"}


@pytest.mark.asyncio
class TestRiskManagerInitialization:
    """Tests for RiskManager initialization."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        mock.add = MagicMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        mock.execute = AsyncMock()
        return mock

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.investment = Decimal("1000")
        mock.update_investment = MagicMock()
        return mock

    async def test_risk_manager_initialization(
        self, mock_db_session: MagicMock, mock_strategy: MagicMock
    ) -> None:
        """RiskManager should initialize with correct attributes."""
        bot_id = uuid4()
        user_id = uuid4()

        with patch("bot.risk_manager.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                risk_default_profile="conservative",
                risk_daily_stop_percent=4.0,
                risk_weekly_stop_percent=10.0,
                risk_monthly_stop_percent=20.0,
                risk_daily_pause_hours=24,
                risk_two_step_wait_minutes=30,
                risk_trailing_percent=3.0,
                risk_trailing_wait_minutes=30,
                risk_active_capital_percent=60.0,
                risk_reserve_capital_percent=40.0,
                risk_reinforcement_levels_percent=[8.0, 15.0],
            )

            rm = RiskManager(
                bot_id=bot_id,
                user_id=user_id,
                symbol="BTC/USDT",
                strategy=mock_strategy,
                db_session=mock_db_session,
            )

        assert rm.bot_id == bot_id
        assert rm.user_id == user_id
        assert rm.symbol == "BTC/USDT"
        assert rm.base_symbol == "BTC"
        assert rm.quote_symbol == "USDT"

    async def test_risk_manager_symbol_parsing(
        self, mock_db_session: MagicMock, mock_strategy: MagicMock
    ) -> None:
        """RiskManager should correctly parse symbol."""
        with patch("bot.risk_manager.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                risk_default_profile="conservative",
                risk_daily_stop_percent=4.0,
                risk_weekly_stop_percent=10.0,
                risk_monthly_stop_percent=20.0,
                risk_daily_pause_hours=24,
                risk_two_step_wait_minutes=30,
                risk_trailing_percent=3.0,
                risk_trailing_wait_minutes=30,
                risk_active_capital_percent=60.0,
                risk_reserve_capital_percent=40.0,
                risk_reinforcement_levels_percent=[8.0, 15.0],
            )

            rm = RiskManager(
                bot_id=uuid4(),
                user_id=uuid4(),
                symbol="ETH/BTC",
                strategy=mock_strategy,
                db_session=mock_db_session,
            )

        assert rm.base_symbol == "ETH"
        assert rm.quote_symbol == "BTC"


@pytest.mark.asyncio
class TestRiskManagerUpdateState:
    """Tests for RiskManager.update_state method."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        mock.add = MagicMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        # Return None for first execute (no existing state)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        mock.execute = AsyncMock(return_value=result_mock)
        return mock

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.investment = Decimal("10000")
        mock.update_investment = MagicMock()
        return mock

    @pytest.fixture
    def risk_manager(
        self, mock_db_session: MagicMock, mock_strategy: MagicMock
    ) -> RiskManager:
        """Create RiskManager instance."""
        with patch("bot.risk_manager.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                risk_default_profile="conservative",
                risk_daily_stop_percent=4.0,
                risk_weekly_stop_percent=10.0,
                risk_monthly_stop_percent=20.0,
                risk_daily_pause_hours=24,
                risk_two_step_wait_minutes=30,
                risk_trailing_percent=3.0,
                risk_trailing_wait_minutes=30,
                risk_active_capital_percent=60.0,
                risk_reserve_capital_percent=40.0,
                risk_reinforcement_levels_percent=[8.0, 15.0],
            )

            return RiskManager(
                bot_id=uuid4(),
                user_id=uuid4(),
                symbol="BTC/USDT",
                strategy=mock_strategy,
                db_session=mock_db_session,
            )

    async def test_evaluate_risk_returns_ok_when_within_limits(
        self, risk_manager: RiskManager
    ) -> None:
        """Should return OK when equity is within acceptable limits."""
        # Set up initial state with 10000 equity
        balance = {
            "total": {"USDT": 9000.0, "BTC": 0.02},  # 9000 + 0.02*50000 = 10000
        }

        decision = await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance,
        )

        assert decision.status == RiskStatus.OK
        assert decision.action == RiskAction.NONE

    async def test_evaluate_risk_returns_none_when_balance_is_none(
        self, risk_manager: RiskManager
    ) -> None:
        """Should return last decision when balance is None."""
        decision = await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=None,
        )

        # Should return the default last decision
        assert decision.status == RiskStatus.OK
        assert decision.action == RiskAction.NONE

    async def test_check_daily_stop_triggers_at_threshold(
        self, risk_manager: RiskManager, mock_db_session: MagicMock
    ) -> None:
        """Should trigger daily stop at 4% drawdown."""
        # First call to create state with 10000 equity
        balance_initial = {"total": {"USDT": 10000.0, "BTC": 0.0}}
        await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_initial,
        )

        # Now simulate 4% drawdown (10000 -> 9600)
        balance_drawdown = {"total": {"USDT": 9600.0, "BTC": 0.0}}
        decision = await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_drawdown,
        )

        assert decision.status == RiskStatus.PAUSED
        assert decision.action == RiskAction.PAUSE
        assert decision.reason == "daily_stop"

    async def test_check_weekly_stop_starts_pending_liquidation(
        self, risk_manager: RiskManager, mock_db_session: MagicMock
    ) -> None:
        """Should start pending liquidation at 10% weekly drawdown."""
        # First call to create state with 10000 equity
        balance_initial = {"total": {"USDT": 10000.0, "BTC": 0.0}}
        await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_initial,
        )

        # Now simulate 10% drawdown (10000 -> 9000)
        balance_drawdown = {"total": {"USDT": 9000.0, "BTC": 0.0}}
        decision = await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_drawdown,
        )

        assert decision.status == RiskStatus.PENDING_LIQUIDATION
        assert decision.action == RiskAction.PENDING_LIQUIDATION
        assert decision.reason == "weekly_stop"

    async def test_check_monthly_stop_starts_pending_liquidation(
        self, risk_manager: RiskManager, mock_db_session: MagicMock
    ) -> None:
        """Should start pending liquidation at 20% monthly drawdown."""
        # First call to create state with 10000 equity
        balance_initial = {"total": {"USDT": 10000.0, "BTC": 0.0}}
        await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_initial,
        )

        # Now simulate 20% drawdown (10000 -> 8000)
        balance_drawdown = {"total": {"USDT": 8000.0, "BTC": 0.0}}
        decision = await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_drawdown,
        )

        assert decision.status == RiskStatus.PENDING_LIQUIDATION
        assert decision.action == RiskAction.PENDING_LIQUIDATION
        assert decision.reason == "monthly_stop"


@pytest.mark.asyncio
class TestRiskManagerTrailingStop:
    """Tests for trailing stop functionality."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        mock.add = MagicMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        mock.execute = AsyncMock(return_value=result_mock)
        return mock

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.investment = Decimal("10000")
        mock.update_investment = MagicMock()
        return mock

    @pytest.fixture
    def risk_manager(
        self, mock_db_session: MagicMock, mock_strategy: MagicMock
    ) -> RiskManager:
        """Create RiskManager instance."""
        with patch("bot.risk_manager.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                risk_default_profile="conservative",
                risk_daily_stop_percent=4.0,
                risk_weekly_stop_percent=10.0,
                risk_monthly_stop_percent=20.0,
                risk_daily_pause_hours=24,
                risk_two_step_wait_minutes=30,
                risk_trailing_percent=3.0,
                risk_trailing_wait_minutes=30,
                risk_active_capital_percent=60.0,
                risk_reserve_capital_percent=40.0,
                risk_reinforcement_levels_percent=[8.0, 15.0],
            )

            return RiskManager(
                bot_id=uuid4(),
                user_id=uuid4(),
                symbol="BTC/USDT",
                strategy=mock_strategy,
                db_session=mock_db_session,
            )

    async def test_check_trailing_stop_activates(
        self, risk_manager: RiskManager
    ) -> None:
        """Should activate trailing stop at 3% drawdown from peak."""
        # First call: establish peak at 10000
        balance_peak = {"total": {"USDT": 10000.0, "BTC": 0.0}}
        await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_peak,
        )

        # Grow to 11000 to establish higher peak
        balance_higher_peak = {"total": {"USDT": 11000.0, "BTC": 0.0}}
        await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_higher_peak,
        )

        # Now 3%+ drawdown from peak (11000 -> 10650)
        # Threshold is 11000 * 0.97 = 10670, so 10650 is below it
        balance_drawdown = {"total": {"USDT": 10650.0, "BTC": 0.0}}
        decision = await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance_drawdown,
        )

        assert decision.status == RiskStatus.PAUSED
        assert decision.action == RiskAction.PAUSE
        assert decision.reason == "trailing_pause"

    async def test_check_trailing_stop_updates_high_water_mark(
        self, risk_manager: RiskManager
    ) -> None:
        """Should update equity peak when it increases."""
        # First call: establish peak at 10000
        balance1 = {"total": {"USDT": 10000.0, "BTC": 0.0}}
        await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance1,
        )

        # Second call: equity grows to 11000
        balance2 = {"total": {"USDT": 11000.0, "BTC": 0.0}}
        await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance2,
        )

        # Peak should be updated
        assert risk_manager._state.equity_peak == Decimal("11000")


@pytest.mark.asyncio
class TestRiskManagerCheckOrder:
    """Tests for check_order method."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        return mock

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.investment = Decimal("10000")
        return mock

    @pytest.fixture
    def risk_manager(
        self, mock_db_session: MagicMock, mock_strategy: MagicMock
    ) -> RiskManager:
        """Create RiskManager instance."""
        with patch("bot.risk_manager.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                risk_default_profile="conservative",
                risk_daily_stop_percent=4.0,
                risk_weekly_stop_percent=10.0,
                risk_monthly_stop_percent=20.0,
                risk_daily_pause_hours=24,
                risk_two_step_wait_minutes=30,
                risk_trailing_percent=3.0,
                risk_trailing_wait_minutes=30,
                risk_active_capital_percent=60.0,
                risk_reserve_capital_percent=40.0,
                risk_reinforcement_levels_percent=[8.0, 15.0],
            )

            return RiskManager(
                bot_id=uuid4(),
                user_id=uuid4(),
                symbol="BTC/USDT",
                strategy=mock_strategy,
                db_session=mock_db_session,
            )

    def test_check_order_allows_when_no_state(self, risk_manager: RiskManager) -> None:
        """Should allow orders when no state is loaded."""
        from bot.strategies.base import Order

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.01"),
        )

        result = risk_manager.check_order(order, Decimal("50000"))
        assert result is True

    def test_check_order_blocks_when_paused(self, risk_manager: RiskManager) -> None:
        """Should block orders when status is PAUSED."""
        from bot.strategies.base import Order

        # Simulate paused state
        risk_manager._state = MagicMock()
        risk_manager._state.status = RiskStatus.PAUSED.value

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.01"),
        )

        result = risk_manager.check_order(order, Decimal("50000"))
        assert result is False

    def test_check_order_blocks_when_pending_liquidation(
        self, risk_manager: RiskManager
    ) -> None:
        """Should block orders when pending liquidation."""
        from bot.strategies.base import Order

        risk_manager._state = MagicMock()
        risk_manager._state.status = RiskStatus.PENDING_LIQUIDATION.value

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.01"),
        )

        result = risk_manager.check_order(order, Decimal("50000"))
        assert result is False

    def test_check_order_blocks_when_liquidated(
        self, risk_manager: RiskManager
    ) -> None:
        """Should block orders when liquidated."""
        from bot.strategies.base import Order

        risk_manager._state = MagicMock()
        risk_manager._state.status = RiskStatus.LIQUIDATED.value

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.01"),
        )

        result = risk_manager.check_order(order, Decimal("50000"))
        assert result is False


@pytest.mark.asyncio
class TestRiskManagerIsTradingAllowed:
    """Tests for is_trading_allowed method."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        return mock

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.investment = Decimal("10000")
        return mock

    @pytest.fixture
    def risk_manager(
        self, mock_db_session: MagicMock, mock_strategy: MagicMock
    ) -> RiskManager:
        """Create RiskManager instance."""
        with patch("bot.risk_manager.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                risk_default_profile="conservative",
                risk_daily_stop_percent=4.0,
                risk_weekly_stop_percent=10.0,
                risk_monthly_stop_percent=20.0,
                risk_daily_pause_hours=24,
                risk_two_step_wait_minutes=30,
                risk_trailing_percent=3.0,
                risk_trailing_wait_minutes=30,
                risk_active_capital_percent=60.0,
                risk_reserve_capital_percent=40.0,
                risk_reinforcement_levels_percent=[8.0, 15.0],
            )

            return RiskManager(
                bot_id=uuid4(),
                user_id=uuid4(),
                symbol="BTC/USDT",
                strategy=mock_strategy,
                db_session=mock_db_session,
            )

    def test_trading_allowed_when_no_state(self, risk_manager: RiskManager) -> None:
        """Should allow trading when no state exists."""
        assert risk_manager.is_trading_allowed() is True

    def test_trading_allowed_when_status_ok(self, risk_manager: RiskManager) -> None:
        """Should allow trading when status is OK."""
        risk_manager._state = MagicMock()
        risk_manager._state.status = RiskStatus.OK.value

        assert risk_manager.is_trading_allowed() is True

    def test_trading_not_allowed_when_paused(self, risk_manager: RiskManager) -> None:
        """Should not allow trading when paused."""
        risk_manager._state = MagicMock()
        risk_manager._state.status = RiskStatus.PAUSED.value

        assert risk_manager.is_trading_allowed() is False


@pytest.mark.asyncio
class TestRiskManagerPauseResume:
    """Tests for pause and resume functionality."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        mock.add = MagicMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        mock.execute = AsyncMock(return_value=result_mock)
        return mock

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.investment = Decimal("10000")
        mock.update_investment = MagicMock()
        return mock

    @pytest.fixture
    def risk_manager(
        self, mock_db_session: MagicMock, mock_strategy: MagicMock
    ) -> RiskManager:
        """Create RiskManager instance."""
        with patch("bot.risk_manager.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                risk_default_profile="conservative",
                risk_daily_stop_percent=4.0,
                risk_weekly_stop_percent=10.0,
                risk_monthly_stop_percent=20.0,
                risk_daily_pause_hours=24,
                risk_two_step_wait_minutes=30,
                risk_trailing_percent=3.0,
                risk_trailing_wait_minutes=30,
                risk_active_capital_percent=60.0,
                risk_reserve_capital_percent=40.0,
                risk_reinforcement_levels_percent=[8.0, 15.0],
            )

            return RiskManager(
                bot_id=uuid4(),
                user_id=uuid4(),
                symbol="BTC/USDT",
                strategy=mock_strategy,
                db_session=mock_db_session,
            )

    async def test_risk_cooldown_period_respected(
        self, risk_manager: RiskManager
    ) -> None:
        """Should return NONE action during cooldown period."""
        # Simulate state with active pause
        now = datetime.now(timezone.utc)
        mock_state = MagicMock(spec=RiskState)
        mock_state.status = RiskStatus.PAUSED.value
        mock_state.paused_until = now + timedelta(hours=12)  # Still paused
        mock_state.pending_liquidation_until = None
        mock_state.trailing_pause_until = None
        mock_state.last_equity = Decimal("10000")
        mock_state.equity_peak = Decimal("10000")
        mock_state.daily_peak = Decimal("10000")
        mock_state.weekly_peak = Decimal("10000")
        mock_state.monthly_peak = Decimal("10000")
        mock_state.daily_window_start = now
        mock_state.weekly_window_start = now
        mock_state.monthly_window_start = now
        mock_state.reinforcements_used = 0
        mock_state.reference_price = Decimal("50000")

        risk_manager._state = mock_state

        balance = {"total": {"USDT": 10000.0, "BTC": 0.0}}
        decision = await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance,
        )

        # Should return PAUSED with no action (still in cooldown)
        assert decision.status == RiskStatus.PAUSED
        assert decision.action == RiskAction.NONE
        assert decision.reason == "daily_pause"

    async def test_risk_status_resumes_after_pause_expires(
        self, risk_manager: RiskManager
    ) -> None:
        """Should resume after pause period expires."""
        # Simulate state with expired pause
        now = datetime.now(timezone.utc)
        mock_state = MagicMock(spec=RiskState)
        mock_state.status = RiskStatus.PAUSED.value
        mock_state.paused_until = now - timedelta(hours=1)  # Expired
        mock_state.pending_liquidation_until = None
        mock_state.trailing_pause_until = None
        mock_state.last_equity = Decimal("10000")
        mock_state.equity_peak = Decimal("10000")
        mock_state.daily_peak = Decimal("10000")
        mock_state.weekly_peak = Decimal("10000")
        mock_state.monthly_peak = Decimal("10000")
        mock_state.daily_window_start = now
        mock_state.weekly_window_start = now
        mock_state.monthly_window_start = now
        mock_state.reinforcements_used = 0
        mock_state.reference_price = Decimal("50000")

        risk_manager._state = mock_state

        balance = {"total": {"USDT": 10000.0, "BTC": 0.0}}
        decision = await risk_manager.update_state(
            current_price=Decimal("50000"),
            balance=balance,
        )

        # Should resume
        assert decision.status == RiskStatus.OK
        assert decision.action == RiskAction.RESUME
        assert decision.reason == "daily_pause_ended"


@pytest.mark.asyncio
class TestRiskManagerLoadState:
    """Tests for state loading and persistence."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        mock.add = MagicMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        return mock

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.investment = Decimal("10000")
        mock.update_investment = MagicMock()
        return mock

    @pytest.fixture
    def risk_manager(
        self, mock_db_session: MagicMock, mock_strategy: MagicMock
    ) -> RiskManager:
        """Create RiskManager instance."""
        with patch("bot.risk_manager.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                risk_default_profile="conservative",
                risk_daily_stop_percent=4.0,
                risk_weekly_stop_percent=10.0,
                risk_monthly_stop_percent=20.0,
                risk_daily_pause_hours=24,
                risk_two_step_wait_minutes=30,
                risk_trailing_percent=3.0,
                risk_trailing_wait_minutes=30,
                risk_active_capital_percent=60.0,
                risk_reserve_capital_percent=40.0,
                risk_reinforcement_levels_percent=[8.0, 15.0],
            )

            return RiskManager(
                bot_id=uuid4(),
                user_id=uuid4(),
                symbol="BTC/USDT",
                strategy=mock_strategy,
                db_session=mock_db_session,
            )

    async def test_load_state_finds_existing_state(
        self, risk_manager: RiskManager, mock_db_session: MagicMock
    ) -> None:
        """Should load existing state from database."""
        mock_state = MagicMock(spec=RiskState)
        mock_state.investment_override = None

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=mock_state)
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        await risk_manager.load_state()

        assert risk_manager._state == mock_state

    async def test_load_state_applies_investment_override(
        self,
        risk_manager: RiskManager,
        mock_db_session: MagicMock,
        mock_strategy: MagicMock,
    ) -> None:
        """Should apply investment override when loading state."""
        mock_state = MagicMock(spec=RiskState)
        mock_state.investment_override = Decimal("15000")

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=mock_state)
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        await risk_manager.load_state()

        mock_strategy.update_investment.assert_called_once_with(Decimal("15000"))

    async def test_load_state_handles_no_existing_state(
        self, risk_manager: RiskManager, mock_db_session: MagicMock
    ) -> None:
        """Should handle case when no state exists."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        await risk_manager.load_state()

        assert risk_manager._state is None


class TestRiskManagerHelpers:
    """Tests for helper methods."""

    def test_split_symbol_with_slash(self) -> None:
        """Should split symbol with slash."""
        base, quote = RiskManager._split_symbol("BTC/USDT")
        assert base == "BTC"
        assert quote == "USDT"

    def test_split_symbol_without_slash(self) -> None:
        """Should handle symbol without slash."""
        base, quote = RiskManager._split_symbol("BTCUSDT")
        assert base == "BTCUSDT"
        assert quote == "USDT"

    def test_split_symbol_with_multiple_slashes(self) -> None:
        """Should only split on first slash."""
        base, quote = RiskManager._split_symbol("BTC/USDT/TEST")
        assert base == "BTC"
        assert quote == "USDT/TEST"
