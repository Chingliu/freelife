from __future__ import annotations

from app.config.settings import Settings
from app.data.mock_provider import MockProvider
from app.data.registry import DEFAULT_REGISTRY


def test_settings_defaults() -> None:
    s = Settings.from_dict({})
    assert s.data.provider == "mock"
    assert s.targets.annual_return_min == 0.05


def test_mock_provider_basic() -> None:
    p = MockProvider()
    assert p.provider_id == "mock"
    stocks = p.get_stock_list()
    assert len(stocks) >= 2
    bars = p.get_daily_bars(stocks[0].code)
    assert len(bars) > 10
    assert p.get_finance(stocks[0].code) is not None
    assert p.get_data_as_of() is not None


def test_registry_creates_mock() -> None:
    s = Settings.from_dict({"data": {"provider": "mock"}})
    p = DEFAULT_REGISTRY.create(s)
    assert p.provider_id == "mock"
    sync = DEFAULT_REGISTRY.create_sync(s, p)
    assert sync is not None
    result = sync.sync()
    assert result.ok
