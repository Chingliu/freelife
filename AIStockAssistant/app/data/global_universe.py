from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GlobalSymbol:
    symbol: str  # Yahoo Finance symbol
    name: str
    region: str  # us / eu / apac
    kind: str  # index / equity
    aliases: tuple[str, ...] = ()


# Minimal watchlist: major EU/US/APAC indices + mega-caps.
GLOBAL_UNIVERSE: tuple[GlobalSymbol, ...] = (
    GlobalSymbol("^GSPC", "S&P 500", "us", "index", ("spx", "sp500", "标普", "标普500")),
    GlobalSymbol("^IXIC", "NASDAQ Composite", "us", "index", ("nasdaq", "纳指", "纳斯达克")),
    GlobalSymbol("^DJI", "Dow Jones", "us", "index", ("dji", "dow", "道指", "道琼斯")),
    GlobalSymbol("^STOXX50E", "EURO STOXX 50", "eu", "index", ("stoxx50", "欧洲50")),
    GlobalSymbol("^GDAXI", "DAX", "eu", "index", ("dax", "德国dax")),
    GlobalSymbol("^FTSE", "FTSE 100", "eu", "index", ("ftse", "富时100")),
    GlobalSymbol("^N225", "Nikkei 225", "apac", "index", ("n225", "nikkei", "日经", "日经225")),
    GlobalSymbol("^HSI", "Hang Seng", "apac", "index", ("hsi", "恒生", "恒指")),
    GlobalSymbol("AAPL", "Apple", "us", "equity", ("苹果",)),
    GlobalSymbol("MSFT", "Microsoft", "us", "equity", ("微软",)),
    GlobalSymbol("NVDA", "NVIDIA", "us", "equity", ("英伟达",)),
    GlobalSymbol("GOOGL", "Alphabet", "us", "equity", ("谷歌", "google")),
    GlobalSymbol("AMZN", "Amazon", "us", "equity", ("亚马逊", "amazon")),
    GlobalSymbol("META", "Meta", "us", "equity", ("脸书", "facebook")),
    GlobalSymbol("TSLA", "Tesla", "us", "equity", ("特斯拉",)),
    GlobalSymbol("0700.HK", "Tencent", "apac", "equity", ("0700", "腾讯", "tencent")),
    GlobalSymbol("BABA", "Alibaba ADR", "apac", "equity", ("阿里", "alibaba")),
)


def _alias_key(text: str) -> str:
    return text.strip().lower().replace(" ", "").replace("．", ".")


_ALIAS_TO_SYMBOL: dict[str, str] = {}
for _item in GLOBAL_UNIVERSE:
    _ALIAS_TO_SYMBOL[_alias_key(_item.symbol)] = _item.symbol
    _ALIAS_TO_SYMBOL[_alias_key(_item.name)] = _item.symbol
    for _a in _item.aliases:
        _ALIAS_TO_SYMBOL[_alias_key(_a)] = _item.symbol


def resolve_global_symbol(code: str) -> str | None:
    """Map user input / alias to Yahoo symbol, or None if unknown."""
    key = _alias_key(code)
    if key in _ALIAS_TO_SYMBOL:
        return _ALIAS_TO_SYMBOL[key]
    # Allow direct Yahoo symbols not in the minimal set (best-effort).
    if any(ch.isalpha() for ch in code) or code.startswith("^") or ".HK" in code.upper():
        return code.strip()
    return None


def list_global_universe(
    region: str | None = None,
    kind: str | None = None,
) -> list[GlobalSymbol]:
    items = list(GLOBAL_UNIVERSE)
    if region:
        r = region.strip().lower()
        items = [x for x in items if x.region == r]
    if kind:
        k = kind.strip().lower()
        items = [x for x in items if x.kind == k]
    return items
