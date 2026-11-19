"""Unit tests for seven-layer selection engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.selection.factors import percentile_scores
from app.selection.service import SelectionService
from app.selection.testing import SelectionMockProvider
from app.selection.universe import load_universe, write_index_file


@pytest.fixture()
def universe_dir(tmp_path: Path) -> Path:
    codes = [
        "sh600519",
        "sz300750",
        "sh600036",
        "sz000858",
        "sz002594",
        "sh601318",
        "sz000333",
        "sh600887",
        "sz002415",
        "sh601012",
        "sz000001",
        "sh600030",
        "sz300014",
        "sz002230",
        "sh600900",
    ]
    write_index_file(tmp_path / "sse50.json", index="sse50", codes=codes[:8], source="test")
    write_index_file(tmp_path / "csi300.json", index="csi300", codes=codes, source="test")
    write_index_file(tmp_path / "csi500.json", index="csi500", codes=codes[8:], source="test")
    (tmp_path / "sectors.json").write_text(
        json.dumps(
            {
                "map": {
                    "sh600519": "消费",
                    "sz300750": "制造",
                    "sh600036": "金融",
                    "sz000858": "消费",
                    "sz002594": "制造",
                    "sh601318": "金融",
                    "sz000333": "制造",
                    "sh600887": "消费",
                    "sz002415": "科技",
                    "sh601012": "制造",
                    "sz000001": "金融",
                    "sh600030": "金融",
                    "sz300014": "制造",
                    "sz002230": "科技",
                    "sh600900": "公用",
                },
                "macro": {"scale": 1.0, "regime_hint": "sideways"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "names.json").write_text(
        json.dumps({"map": {"sh600519": "贵州茅台", "sz300750": "宁德时代"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "finance_cache.json").write_text(
        json.dumps(
            {
                "items": {
                    "sh600519": {"pe": 28, "pb": 9.5, "roe": 0.30, "profit_cagr": 0.12},
                    "sz300750": {"pe": 22, "pb": 4.0, "roe": 0.18, "profit_cagr": 0.20},
                    "sh600036": {"pe": 7.5, "pb": 1.0, "roe": 0.16, "profit_cagr": 0.08},
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "capital_flow.json").write_text(
        json.dumps(
            {
                "items": {
                    "sh600519": {"net_inflow_5d": 1e8, "northbound_days": 5},
                    "sz300750": {"net_inflow_5d": 8e7, "northbound_days": 3},
                },
                "macro": {"scale": 0.95, "regime_hint": "sideways"},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def svc(universe_dir: Path) -> SelectionService:
    settings = Settings.from_dict({"data": {"provider": "mock"}})
    return SelectionService(
        settings=settings,
        provider=SelectionMockProvider(),
        universe_dir=universe_dir,
    )


def test_percentile_scores_invert() -> None:
    raw = {"a": 1.0, "b": 2.0, "c": 3.0}
    hi = percentile_scores(raw, higher_is_better=True)
    lo = percentile_scores(raw, higher_is_better=False)
    assert hi["c"] == 100.0
    assert lo["c"] == 0.0


def test_load_universe(universe_dir: Path) -> None:
    uni = load_universe(universe_dir)
    assert len(uni.codes) == 15
    assert "csi300" in uni.by_index


def test_run_daily_top10(svc: SelectionService) -> None:
    out = svc.run_daily(top_n=10)
    assert out["provider_id"] == "selection_mock"
    assert out["scored_count"] >= 10
    top = out["top10"]
    assert 1 <= len(top) <= 10
    assert top[0]["rank"] == 1
    assert top[0]["composite"] is not None
    # sector cap: no more than 3 of same sector
    from collections import Counter

    counts = Counter(r["sector"] for r in top)
    assert all(v <= 3 for v in counts.values())


def test_stock_report_has_evidence(svc: SelectionService) -> None:
    daily = svc.run_daily(top_n=5)
    code = daily["top10"][0]["code"]
    rep = svc.stock_report(code)
    assert rep.get("reasons")
    assert len(rep["reasons"]) >= 1
    assert rep.get("evidence")
    assert "evidence_grade" in rep
    assert rep.get("entry_zone")
    assert rep.get("stop_loss")
    assert "disclaimer" in rep


def test_phase3_value_factors_present(svc: SelectionService) -> None:
    daily = svc.run_daily(top_n=10)
    # At least one name with finance should expose value_ep status ok
    found = False
    for row in daily["top10"]:
        fv = (row.get("factors") or {}).get("value_ep")
        if fv and fv.get("status") == "ok":
            found = True
            break
    # If top10 has no finance names, check scored pool via stock report on 600519
    if not found:
        rep = svc.stock_report("sh600519")
        assert rep["factors"]["value_ep"]["status"] == "ok"
        found = True
    assert found


def test_phase4_flow_and_macro(svc: SelectionService) -> None:
    rep = svc.stock_report("sh600519")
    assert rep["factors"]["flow_inflow_5d"]["status"] == "ok"
    # macro scale 0.95 applied to composites in scoring — composite should exist
    assert rep["composite"] is not None


def test_factor_validation_lifecycle(svc: SelectionService) -> None:
    out = svc.factor_validation("mom_20", months=12, refresh=True)
    assert out["ok"] is True
    fac = out["factor"]
    assert fac["factor_id"] == "mom_20"
    assert fac["lifecycle"] in {"active", "watch", "demoted"}
    assert "rank_ic_1y" in fac


def test_data_status(svc: SelectionService) -> None:
    st = svc.data_status()
    assert "universe" in st
    assert "factor_catalog" in st
    assert st["meta"]["finance_cache"] is True
