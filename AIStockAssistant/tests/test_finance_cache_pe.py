"""Unit tests for finance_cache mapping and live PE/PB."""

from __future__ import annotations

from pathlib import Path

from app.data.pytdx_finance import map_finance_info, merge_finance_item, write_finance_cache_blob
from app.selection.factors import fundamental as fund_f
from app.selection.meta.finance import finance_with_price, load_finance_cache


def test_map_finance_info_eps_bps_roe() -> None:
    # Values as returned by pytdx (already *10000 for yuan/shares).
    raw = {
        "jinglirun": 1_000_000_000.0,
        "jingzichan": 5_000_000_000.0,
        "zongguben": 500_000_000.0,
        "meigujingzichan": 10.0,
        "updated_date": 20260430,
    }
    mapped = map_finance_info(raw)
    assert mapped is not None
    assert mapped["eps"] == 2.0  # 1e9 / 5e8
    assert mapped["bps"] == 10.0
    assert mapped["roe"] == 0.2
    assert mapped["updated_date"] == 20260430
    assert mapped["bps_crosscheck_ok"] is True
    assert mapped["source"] == "pytdx.get_finance_info"


def test_map_finance_info_skips_losses() -> None:
    raw = {
        "jinglirun": -1_000_000.0,
        "jingzichan": 5_000_000_000.0,
        "zongguben": 500_000_000.0,
        "meigujingzichan": 10.0,
    }
    mapped = map_finance_info(raw)
    assert mapped is not None
    assert "eps" not in mapped
    assert "roe" not in mapped
    assert mapped["bps"] == 10.0


def test_merge_preserves_profit_cagr_and_drops_stale_pe() -> None:
    existing = {"pe": 28.0, "pb": 9.5, "roe": 0.3, "profit_cagr": 0.12}
    mapped = {"eps": 40.0, "bps": 100.0, "roe": 0.31, "source": "pytdx.get_finance_info"}
    merged = merge_finance_item(existing, mapped)
    assert merged["eps"] == 40.0
    assert merged["profit_cagr"] == 0.12
    assert "pe" not in merged
    assert "pb" not in merged
    assert merged["roe"] == 0.31


def test_finance_with_price_computes_pe_pb() -> None:
    fin = finance_with_price(
        "sh600519",
        cache_row={"eps": 50.0, "bps": 200.0, "roe": 0.25, "profit_cagr": 0.1},
        last_close=1500.0,
        price_as_of="2026-08-05",
    )
    assert fin is not None
    assert fin.pe == 30.0
    assert fin.pb == 7.5
    assert fin.roe == 0.25
    assert fin.extras.get("pe_source") == "local_close/eps"
    assert fund_f.value_ep(fin) == 1.0 / 30.0
    assert fund_f.value_bp(fin) == 1.0 / 7.5
    assert fund_f.quality_profit_cagr(fin) == 0.1


def test_legacy_pe_pb_without_eps() -> None:
    fin = finance_with_price(
        "sh600036",
        cache_row={"pe": 7.5, "pb": 1.0, "roe": 0.16},
        last_close=40.0,
    )
    assert fin is not None
    assert fin.pe == 7.5
    assert fin.pb == 1.0


def test_load_finance_cache_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "finance_cache.json"
    write_finance_cache_blob(
        path,
        {
            "as_of": "2026-08-05",
            "items": {
                "sh600519": {"eps": 47.0, "bps": 140.0, "roe": 0.3, "profit_cagr": 0.12},
            },
        },
    )
    loaded = load_finance_cache(path)
    assert "sh600519" in loaded
    assert loaded["sh600519"].roe == 0.3
    assert loaded["sh600519"].extras.get("eps") == 47.0
    priced = finance_with_price(
        "sh600519",
        fin=loaded["sh600519"],
        last_close=1410.0,
    )
    assert priced is not None
    assert abs((priced.pe or 0) - 30.0) < 1e-9
