"""
Comprehensive Unit Tests for Backtest Service.

Tests for historical data loading and strategy simulation covering:
- run_and_store creates backtest record
- Simulate grid/dca strategies
- Fetch OHLCV from exchange/cache
- Calculate PnL and respect date range
- Handle insufficient data
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import Backtest
from api.services.backtest_service import (
    BacktestService,
    Candle,
    SimTrade,
)


class TestCandle:
    """Tests for Candle dataclass."""

    def test_candle_creation(self) -> None:
        """Should create candle with all fields."""
        now = datetime.now(timezone.utc)
        candle = Candle(
            timestamp=now,
            open=50000.0,
            high=51000.0,
            low=49000.0,
            close=50500.0,
            volume=100.0,
        )

        assert candle.timestamp == now
        assert candle.open == 50000.0
        assert candle.high == 51000.0
        assert candle.low == 49000.0
        assert candle.close == 50500.0
        assert candle.volume == 100.0


class TestSimTrade:
    """Tests for SimTrade dataclass."""

    def test_sim_trade_creation(self) -> None:
        """Should create simulated trade."""
        now = datetime.now(timezone.utc)
        trade = SimTrade(
            timestamp=now,
            side="buy",
            price=50000.0,
            quantity=0.01,
            realized_pnl=0.0,
        )

        assert trade.timestamp == now
        assert trade.side == "buy"
        assert trade.price == 50000.0
        assert trade.quantity == 0.01
        assert trade.realized_pnl == 0.0


@pytest.mark.asyncio
class TestBacktestServiceRunAndStore:
    """Tests for BacktestService.run_and_store method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        mock.add = MagicMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        return mock

    @pytest.fixture
    def backtest_service(self, mock_db: MagicMock) -> BacktestService:
        """Create backtest service instance."""
        return BacktestService(mock_db)

    @pytest.fixture
    def sample_candles(self) -> list[Candle]:
        """Create sample candles for testing."""
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        candles = []
        prices = [50000, 49500, 49000, 48500, 49000, 49500, 50000, 50500, 51000, 50500]

        for i, price in enumerate(prices):
            candles.append(
                Candle(
                    timestamp=base_time + timedelta(hours=i),
                    open=price - 100,
                    high=price + 200,
                    low=price - 200,
                    close=price,
                    volume=100.0,
                )
            )
        return candles

    async def test_run_and_store_creates_backtest_record(
        self,
        backtest_service: BacktestService,
        mock_db: MagicMock,
        sample_candles: list[Candle],
    ) -> None:
        """Should create and persist backtest record."""
        user_id = uuid4()
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 2, tzinfo=timezone.utc)

        with patch.object(
            backtest_service, "_fetch_ohlcv", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = sample_candles

            result = await backtest_service.run_and_store(
                user_id=user_id,
                strategy="grid",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=start_date,
                end_date=end_date,
                config={
                    "lower_price": 48000,
                    "upper_price": 52000,
                    "grid_count": 10,
                    "investment": 1000,
                },
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert isinstance(result, Backtest)
        assert result.user_id == user_id
        assert result.strategy == "grid"
        assert result.status == "completed"

    async def test_run_and_store_raises_on_no_data(
        self,
        backtest_service: BacktestService,
    ) -> None:
        """Should raise ValueError when no candles returned."""
        with patch.object(
            backtest_service, "_fetch_ohlcv", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = []

            with pytest.raises(ValueError, match="No historical data"):
                await backtest_service.run_and_store(
                    user_id=uuid4(),
                    strategy="grid",
                    symbol="BTC/USDT",
                    timeframe="1h",
                    start_date=datetime.now(timezone.utc),
                    end_date=datetime.now(timezone.utc),
                    config={},
                )


@pytest.mark.asyncio
class TestBacktestServiceGridSimulation:
    """Tests for grid strategy simulation."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def backtest_service(self, mock_db: MagicMock) -> BacktestService:
        """Create backtest service instance."""
        return BacktestService(mock_db)

    def test_simulate_grid_strategy_basic(
        self, backtest_service: BacktestService
    ) -> None:
        """Should simulate grid strategy correctly."""
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # Price moves down then up - should trigger grid trades
        candles = [
            Candle(base_time, 50000, 50100, 49900, 50000, 100),
            Candle(base_time + timedelta(hours=1), 49500, 49600, 49400, 49500, 100),
            Candle(base_time + timedelta(hours=2), 49000, 49100, 48900, 49000, 100),
            Candle(base_time + timedelta(hours=3), 49500, 49600, 49400, 49500, 100),
            Candle(base_time + timedelta(hours=4), 50000, 50100, 49900, 50000, 100),
            Candle(base_time + timedelta(hours=5), 50500, 50600, 50400, 50500, 100),
        ]

        config = {
            "lower_price": 48000,
            "upper_price": 52000,
            "grid_count": 10,
            "investment": 1000,
        }

        results = backtest_service._simulate_grid(candles, config)

        assert "total_return" in results
        assert "sharpe_ratio" in results
        assert "max_drawdown" in results
        assert "win_rate" in results
        assert "profit_factor" in results
        assert "total_trades" in results
        assert "equity_curve" in results
        assert results["total_trades"] > 0

    def test_simulate_grid_strategy_empty_with_invalid_config(
        self, backtest_service: BacktestService
    ) -> None:
        """Should return empty results with invalid config."""
        candles = [
            Candle(datetime.now(timezone.utc), 50000, 50100, 49900, 50000, 100),
        ]

        # Invalid: upper <= lower
        config = {
            "lower_price": 52000,
            "upper_price": 48000,
            "grid_count": 10,
            "investment": 1000,
        }

        results = backtest_service._simulate_grid(candles, config)

        assert results["total_trades"] == 0
        assert results["total_return"] == 0.0

    def test_simulate_grid_zero_investment(
        self, backtest_service: BacktestService
    ) -> None:
        """Should return empty results with zero investment."""
        candles = [
            Candle(datetime.now(timezone.utc), 50000, 50100, 49900, 50000, 100),
        ]

        config = {
            "lower_price": 48000,
            "upper_price": 52000,
            "grid_count": 10,
            "investment": 0,
        }

        results = backtest_service._simulate_grid(candles, config)

        assert results["total_trades"] == 0


@pytest.mark.asyncio
class TestBacktestServiceDCASimulation:
    """Tests for DCA strategy simulation."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def backtest_service(self, mock_db: MagicMock) -> BacktestService:
        """Create backtest service instance."""
        return BacktestService(mock_db)

    def test_simulate_dca_strategy_basic(
        self, backtest_service: BacktestService
    ) -> None:
        """Should simulate DCA strategy correctly."""
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # Price pattern for DCA
        candles = [
            Candle(base_time, 50000, 50100, 49900, 50000, 100),
            Candle(base_time + timedelta(days=1), 49000, 49100, 48900, 49000, 100),
            Candle(base_time + timedelta(days=2), 48000, 48100, 47900, 48000, 100),
            Candle(base_time + timedelta(days=3), 50000, 50100, 49900, 50000, 100),
            Candle(base_time + timedelta(days=4), 52000, 52100, 51900, 52000, 100),
        ]

        config = {
            "amount": 100,
            "interval": "daily",
            "trigger_drop": None,
            "take_profit": None,
        }

        results = backtest_service._simulate_dca(candles, config)

        assert "total_trades" in results
        assert results["total_trades"] > 0

    def test_simulate_dca_with_trigger_drop(
        self, backtest_service: BacktestService
    ) -> None:
        """Should trigger extra buys on price drops."""
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # 10% drop from 50000 to 45000
        candles = [
            Candle(base_time, 50000, 50100, 49900, 50000, 100),
            Candle(base_time + timedelta(hours=1), 45000, 45100, 44900, 45000, 100),
        ]

        config = {
            "amount": 100,
            "interval": "daily",
            "trigger_drop": 5.0,  # 5% trigger
            "take_profit": None,
        }

        results = backtest_service._simulate_dca(candles, config)

        # Should have bought on first candle and again on 10% drop
        assert results["total_trades"] >= 2

    def test_simulate_dca_with_take_profit(
        self, backtest_service: BacktestService
    ) -> None:
        """Should sell at take profit level."""
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # Buy at 50000, price rises to 56000 (12% gain)
        candles = [
            Candle(base_time, 50000, 50100, 49900, 50000, 100),
            Candle(base_time + timedelta(hours=1), 56000, 56100, 55900, 56000, 100),
        ]

        config = {
            "amount": 100,
            "interval": "daily",
            "trigger_drop": None,
            "take_profit": 10.0,  # 10% take profit
        }

        results = backtest_service._simulate_dca(candles, config)

        # Should have buy and sell trades
        assert results["total_trades"] >= 2

    def test_simulate_dca_zero_amount(self, backtest_service: BacktestService) -> None:
        """Should return empty results with zero amount."""
        candles = [
            Candle(datetime.now(timezone.utc), 50000, 50100, 49900, 50000, 100),
        ]

        config = {
            "amount": 0,
            "interval": "daily",
        }

        results = backtest_service._simulate_dca(candles, config)

        assert results["total_trades"] == 0


@pytest.mark.asyncio
class TestBacktestServiceFetchOHLCV:
    """Tests for OHLCV data fetching."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def backtest_service(self, mock_db: MagicMock) -> BacktestService:
        """Create backtest service instance."""
        return BacktestService(mock_db)

    async def test_fetch_ohlcv_from_exchange(
        self, backtest_service: BacktestService
    ) -> None:
        """Should fetch OHLCV data from exchange."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 2, tzinfo=timezone.utc)

        mock_exchange = MagicMock()
        mock_exchange.parse_timeframe = MagicMock(return_value=3600)  # 1 hour
        mock_exchange.fetch_ohlcv = AsyncMock(
            return_value=[
                [1704067200000, 50000, 50100, 49900, 50000, 100],
                [1704070800000, 50100, 50200, 50000, 50050, 110],
            ]
        )
        mock_exchange.close = AsyncMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            candles = await backtest_service._fetch_ohlcv(
                exchange_id="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=start_date,
                end_date=end_date,
            )

        assert len(candles) > 0
        assert isinstance(candles[0], Candle)
        mock_exchange.close.assert_called_once()

    async def test_fetch_ohlcv_handles_empty_response(
        self, backtest_service: BacktestService
    ) -> None:
        """Should handle empty OHLCV response."""
        mock_exchange = MagicMock()
        mock_exchange.parse_timeframe = MagicMock(return_value=3600)
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=[])
        mock_exchange.close = AsyncMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            candles = await backtest_service._fetch_ohlcv(
                exchange_id="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime.now(timezone.utc) - timedelta(days=1),
                end_date=datetime.now(timezone.utc),
            )

        assert candles == []


@pytest.mark.asyncio
class TestBacktestServiceMetrics:
    """Tests for backtest metrics calculation."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def backtest_service(self, mock_db: MagicMock) -> BacktestService:
        """Create backtest service instance."""
        return BacktestService(mock_db)

    def test_calculate_sharpe_ratio(self, backtest_service: BacktestService) -> None:
        """Should calculate Sharpe ratio correctly."""
        # Steady growth
        equity_values = [1000, 1010, 1020, 1030, 1040, 1050]

        sharpe = backtest_service._calculate_sharpe(equity_values)

        assert sharpe > 0  # Positive returns should have positive Sharpe

    def test_calculate_sharpe_ratio_insufficient_data(
        self, backtest_service: BacktestService
    ) -> None:
        """Should return 0 for insufficient data."""
        equity_values = [1000]

        sharpe = backtest_service._calculate_sharpe(equity_values)

        assert sharpe == 0.0

    def test_calculate_max_drawdown(self, backtest_service: BacktestService) -> None:
        """Should calculate max drawdown correctly."""
        # Peak at 1100, trough at 900 = 18.18% drawdown
        equity_values = [1000, 1100, 1000, 900, 950, 1000]

        max_dd = backtest_service._calculate_max_drawdown(equity_values)

        assert 0.18 < max_dd < 0.19

    def test_calculate_max_drawdown_empty(
        self, backtest_service: BacktestService
    ) -> None:
        """Should return 0 for empty values."""
        max_dd = backtest_service._calculate_max_drawdown([])
        assert max_dd == 0.0

    def test_downsample_equity(self, backtest_service: BacktestService) -> None:
        """Should downsample equity curve to max points."""
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # Create 500 points
        equity_points = [(base_time + timedelta(hours=i), 1000 + i) for i in range(500)]

        downsampled = backtest_service._downsample_equity(equity_points, max_points=100)

        assert len(downsampled) <= 101  # max_points + possibly 1 for last

    def test_downsample_equity_preserves_small_dataset(
        self, backtest_service: BacktestService
    ) -> None:
        """Should not downsample if under max_points."""
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        equity_points = [(base_time + timedelta(hours=i), 1000 + i) for i in range(50)]

        downsampled = backtest_service._downsample_equity(equity_points, max_points=100)

        assert len(downsampled) == 50

    def test_build_results(self, backtest_service: BacktestService) -> None:
        """Should build complete results dict."""
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        trades = [
            SimTrade(base_time, "buy", 50000, 0.01, 0),
            SimTrade(base_time + timedelta(hours=1), "sell", 51000, 0.01, 10),
        ]
        equity_points = [
            (base_time, 1000),
            (base_time + timedelta(hours=1), 1010),
        ]

        results = backtest_service._build_results(trades, equity_points, 1000)

        assert results["total_return"] == 0.01  # 1% return
        assert results["total_trades"] == 2
        assert results["win_rate"] == 0.5  # 1 win out of 2
        assert len(results["equity_curve"]) == 2


@pytest.mark.asyncio
class TestBacktestServiceListAndGet:
    """Tests for listing and getting backtests."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database session."""
        mock = MagicMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        return mock

    @pytest.fixture
    def backtest_service(self, mock_db: MagicMock) -> BacktestService:
        """Create backtest service instance."""
        return BacktestService(mock_db)

    async def test_list_for_user(
        self, backtest_service: BacktestService, mock_db: MagicMock
    ) -> None:
        """Should list backtests for user with pagination."""
        user_id = uuid4()

        # Mock the query results
        mock_backtests = [MagicMock(spec=Backtest), MagicMock(spec=Backtest)]
        result_mock = MagicMock()
        result_mock.scalars().all.return_value = mock_backtests

        count_mock = MagicMock()
        count_mock.scalar_one.return_value = 10

        mock_db.execute = AsyncMock(side_effect=[result_mock, count_mock])

        backtests, total = await backtest_service.list_for_user(
            user_id, limit=50, offset=0
        )

        assert len(backtests) == 2
        assert total == 10

    async def test_get_for_user(
        self, backtest_service: BacktestService, mock_db: MagicMock
    ) -> None:
        """Should get specific backtest for user."""
        user_id = uuid4()
        backtest_id = uuid4()

        mock_backtest = MagicMock(spec=Backtest)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_backtest
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await backtest_service.get_for_user(backtest_id, user_id)

        assert result == mock_backtest

    async def test_get_for_user_not_found(
        self, backtest_service: BacktestService, mock_db: MagicMock
    ) -> None:
        """Should return None if backtest not found."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await backtest_service.get_for_user(uuid4(), uuid4())

        assert result is None
