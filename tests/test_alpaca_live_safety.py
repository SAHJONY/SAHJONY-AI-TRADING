"""Broker-boundary safety checks for Alpaca live execution."""

from config import Config
from utils.alpaca_client import AlpacaClient
from utils.sim_broker import SimBroker


class _TradingStub:
    def __init__(self):
        self.submissions = 0

    def submit_order(self, _request):
        self.submissions += 1
        raise AssertionError("an unarmed adapter must never reach Alpaca")


class _BrokenPositions:
    def get_all_positions(self):
        raise ConnectionError("broker unavailable")


def _connected_client(*, paper: bool, acknowledged: bool) -> tuple[AlpacaClient, _TradingStub]:
    cfg = Config(
        alpaca_api_key="test-key",
        alpaca_secret_key="test-secret",
        alpaca_paper=paper,
        live_trading_ack=acknowledged,
    )
    client = AlpacaClient.__new__(AlpacaClient)
    client.cfg = cfg
    client.mode = "paper" if paper else "LIVE"
    trading = _TradingStub()
    client._trading = trading
    client._data = object()
    client._crypto = object()
    client._sim = SimBroker(cfg)
    return client, trading


def test_live_equity_order_is_blocked_inside_adapter_without_acknowledgement():
    client, trading = _connected_client(paper=False, acknowledged=False)

    result = client.submit_equity_order("SPY", 1, "buy")

    assert result == {"status": "rejected", "reason": "live trading is not armed"}
    assert trading.submissions == 0
    assert client.trading_armed is False
    assert client.execution_authority is False


def test_live_option_order_is_blocked_inside_adapter_without_acknowledgement():
    client, trading = _connected_client(paper=False, acknowledged=False)

    result = client.submit_option_order("SPY_TEST_CONTRACT", 1, "buy")

    assert result == {"status": "rejected", "reason": "live trading is not armed"}
    assert trading.submissions == 0


def test_paper_connection_is_armed_without_real_money_acknowledgement():
    client, _ = _connected_client(paper=True, acknowledged=False)

    assert client.trading_armed is True
    assert client.execution_authority is True


def test_live_connection_is_armed_only_with_real_money_acknowledgement():
    client, _ = _connected_client(paper=False, acknowledged=True)

    assert client.trading_armed is True
    assert client.execution_authority is True


def test_canonical_robinhood_configuration_is_detected():
    cfg = Config(
        broker="robinhood_crypto",
        robinhood_api_key="test-key",
        robinhood_private_key="test-private-key",
    )

    assert cfg.venue_configured is True


def test_live_position_snapshot_failure_is_not_reported_as_flat():
    client, _ = _connected_client(paper=False, acknowledged=True)
    client._trading = _BrokenPositions()

    try:
        client.get_broker_positions()
    except RuntimeError as exc:
        assert "snapshot unavailable" in str(exc)
    else:
        raise AssertionError("position read failure must propagate to reconciliation")
