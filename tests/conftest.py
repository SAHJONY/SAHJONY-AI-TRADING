import pytest

from config import load_config


@pytest.fixture
def cfg(monkeypatch):
    """Safe deterministic test configuration with all live trading disabled."""
    monkeypatch.setenv("ROBINHOOD_LIVE", "false")
    monkeypatch.setenv("ROBINHOOD_MCP_LIVE", "false")
    monkeypatch.setenv("LIVE_TRADING_ACK", "")
    monkeypatch.setenv("TRADING_HALT", "false")

    return load_config()
