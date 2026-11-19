from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EtfSpec:
    code: str
    name: str
    index: str
    style: str  # large / mid / small / style / qdii


BROAD_ETFS: tuple[EtfSpec, ...] = (
    EtfSpec("sh510050", "上证50ETF", "上证50", "large"),
    EtfSpec("sh510300", "沪深300ETF", "沪深300", "large"),
    EtfSpec("sh510210", "上证综指ETF", "上证综指", "large"),
    EtfSpec("sh510500", "中证500ETF", "中证500", "mid"),
    EtfSpec("sh512100", "中证1000ETF", "中证1000", "small"),
    EtfSpec("sh588000", "科创50ETF", "科创50", "style"),
    EtfSpec("sz159915", "创业板ETF", "创业板指", "style"),
)

QDII_ETFS: tuple[EtfSpec, ...] = (
    EtfSpec("sh513100", "纳斯达克100ETF", "纳斯达克100", "qdii"),
    EtfSpec("sh513500", "标普500ETF", "标普500", "qdii"),
    EtfSpec("sz159920", "恒生ETF", "恒生指数", "qdii"),
    EtfSpec("sh513180", "恒生科技ETF", "恒生科技", "qdii"),
    EtfSpec("sh513520", "日经225ETF", "日经225", "qdii"),
)

RESEARCH_ETFS: tuple[EtfSpec, ...] = BROAD_ETFS + QDII_ETFS

_BY_CODE: dict[str, EtfSpec] = {e.code: e for e in RESEARCH_ETFS}


def list_broad_etfs() -> list[dict[str, str]]:
    return [_spec_to_dict(e) for e in BROAD_ETFS]


def list_qdii_etfs() -> list[dict[str, str]]:
    return [_spec_to_dict(e) for e in QDII_ETFS]


def list_research_etfs() -> list[dict[str, str]]:
    return [_spec_to_dict(e) for e in RESEARCH_ETFS]


def default_research_codes() -> list[str]:
    return [e.code for e in RESEARCH_ETFS]


def default_broad_codes() -> list[str]:
    return [e.code for e in BROAD_ETFS]


def etf_name(code: str) -> str:
    spec = _BY_CODE.get(code.lower())
    return spec.name if spec else code


def etf_label(code: str) -> str:
    code = code.lower()
    spec = _BY_CODE.get(code)
    if spec:
        return f"{code}（{spec.name}）"
    return code


def _spec_to_dict(e: EtfSpec) -> dict[str, str]:
    return {
        "code": e.code,
        "name": e.name,
        "index": e.index,
        "style": e.style,
    }
