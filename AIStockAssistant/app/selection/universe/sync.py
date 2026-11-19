"""Sync index constituents into local JSON cache.

Priority:
1. Tongdaxin block / T0002 cfg lists under tdx root (best-effort)
2. China Securities Index (中证) official ``*cons.xls`` download
3. Keep existing files and mark stale if sync fails

Official constituents change on CSIndex periodic rebalance (typically
announced late May / late Nov, effective mid-June / mid-December).
Re-run ``selection-sync-universe`` after each生效日 (or anytime) to refresh.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from app.selection.universe import INDEX_FILES, default_universe_dir, load_index_file, write_index_file

logger = logging.getLogger(__name__)

# Common TDX block name hints (GBK filenames vary by install).
_BLOCK_HINTS: dict[str, tuple[str, ...]] = {
    "sse50": ("上证50", "上證50", "sz50", "SSE50"),
    "csi300": ("沪深300", "滬深300", "hs300", "CSI300"),
    "csi500": ("中证500", "中證500", "zz500", "CSI500"),
}

# Official CSIndex constituent workbook (OLE .xls).
_CSINDEX_CODE: dict[str, str] = {
    "sse50": "000016",
    "csi300": "000300",
    "csi500": "000905",
}
_CSINDEX_CONS_URL = (
    "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
    "file/autofile/cons/{code}cons.xls"
)

# Soft size checks — reject obviously truncated TDX hits.
_EXPECTED_MIN: dict[str, int] = {
    "sse50": 40,
    "csi300": 250,
    "csi500": 400,
}


def _to_prefixed(num: str) -> str:
    """Map bare 6-digit A-share code to sh/sz/bj prefix."""
    if num.startswith(("5", "6", "9")):
        return f"sh{num}"
    if num.startswith(("0", "3")):
        return f"sz{num}"
    if num.startswith(("4", "8")):
        return f"bj{num}"
    return f"sh{num}"


def _dedupe(codes: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for c in codes:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _try_read_tdx_block_codes(tdx_root: Path, index_key: str) -> list[str]:
    """Best-effort scan of TDX block text files for index member codes."""
    if not tdx_root.is_dir():
        return []
    hints = _BLOCK_HINTS.get(index_key, ())
    candidates: list[Path] = []
    for sub in ("T0002/blocknew", "T0002/hq_cache", "T0002", "vipdoc"):
        base = tdx_root / sub
        if base.is_dir():
            candidates.extend(base.rglob("*"))
    code_re = re.compile(r"(?:sh|sz|bj)?(\d{6})", re.I)
    found: list[str] = []
    for path in candidates:
        if not path.is_file():
            continue
        name = path.name
        if not any(h.lower() in name.lower() for h in hints):
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        text = ""
        for enc in ("gbk", "utf-8", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        for m in code_re.finditer(text):
            num = m.group(1)
            prefix = "sh" if num.startswith(("5", "6", "9")) else "sz"
            span = text[max(0, m.start() - 2) : m.start()].lower()
            if "sh" in span:
                prefix = "sh"
            elif "sz" in span:
                prefix = "sz"
            elif "bj" in span:
                prefix = "bj"
            found.append(f"{prefix}{num}")
        if found:
            break
    return _dedupe(found)


def _fetch_csindex_cons_xls(index_key: str, *, timeout: float = 45.0) -> list[str]:
    """Download official CSIndex constituent .xls and extract A-share codes."""
    idx_code = _CSINDEX_CODE.get(index_key)
    if not idx_code:
        return []
    url = _CSINDEX_CONS_URL.format(code=idx_code)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AIStockAssistant/1.0)",
            "Referer": "https://www.csindex.com.cn/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("csindex fetch %s failed: %s", index_key, exc)
        return []

    # Workbook is OLE .xls; constituent codes appear as ASCII digit runs.
    nums = {m.decode("ascii") for m in re.findall(rb"(?<![0-9])([0-9]{6})(?![0-9])", raw)}
    nums.discard(idx_code)  # file also embeds the index code itself
    # Keep A-share / STAR / ChiNext / BJ style codes only.
    keep = sorted(
        n
        for n in nums
        if n[:2] in {"00", "30", "60", "68", "43", "83", "87"}
        or n.startswith(("4", "8"))
    )
    return _dedupe([_to_prefixed(n) for n in keep])


def _size_ok(index_key: str, codes: list[str]) -> bool:
    return len(codes) >= _EXPECTED_MIN.get(index_key, 1)


def sync_index_constituents(
    *,
    universe_dir: Path | None = None,
    tdx_root: Path | None = None,
    as_of: date | None = None,
    prefer_csindex: bool = False,
) -> dict[str, Any]:
    """Refresh local universe JSON. Never deletes existing codes on total failure."""
    root = Path(universe_dir) if universe_dir else default_universe_dir()
    root.mkdir(parents=True, exist_ok=True)
    day = as_of or date.today()
    results: dict[str, Any] = {
        "universe_dir": str(root),
        "as_of": day.isoformat(),
        "indices": {},
        "note": (
            "CSIndex 成分通常在每年 6 月 / 12 月中旬生效；"
            "调样后重新运行 selection-sync-universe 即可覆盖本地 JSON。"
        ),
    }

    for key, fname in INDEX_FILES.items():
        path = root / fname
        existing = load_index_file(path)
        codes: list[str] = []
        source = "unchanged"
        stale = True

        tdx_codes: list[str] = []
        cs_codes: list[str] = []
        if tdx_root is not None and not prefer_csindex:
            tdx_codes = _try_read_tdx_block_codes(Path(tdx_root), key)

        use_tdx = bool(tdx_codes) and _size_ok(key, tdx_codes)
        if use_tdx:
            codes = tdx_codes
            source = "tdx_block"
            stale = False
        else:
            if tdx_codes:
                logger.info(
                    "sync %s: TDX hit too small (%s < %s), trying CSIndex",
                    key,
                    len(tdx_codes),
                    _EXPECTED_MIN.get(key),
                )
            cs_codes = _fetch_csindex_cons_xls(key)
            if cs_codes and _size_ok(key, cs_codes):
                codes = cs_codes
                source = "csindex_cons"
                stale = False
            elif cs_codes:
                # Accept partial CSIndex rather than ancient seed when plausible.
                codes = cs_codes
                source = "csindex_cons_partial"
                stale = True
                logger.warning(
                    "sync %s: CSIndex partial count=%s (expected >= %s)",
                    key,
                    len(cs_codes),
                    _EXPECTED_MIN.get(key),
                )

        if codes:
            write_index_file(
                path,
                index=key,
                codes=codes,
                source=source,
                as_of=day,
                stale=stale,
            )
        else:
            codes = list(existing.get("codes") or [])
            if codes:
                write_index_file(
                    path,
                    index=key,
                    codes=codes,
                    source=str(existing.get("source") or "seed"),
                    as_of=existing.get("as_of") or day,
                    stale=True,
                )
                source = f"kept:{existing.get('source')}"
                stale = True
            else:
                source = "empty"
                stale = True
            logger.warning("sync %s: no source hit; kept=%s stale=%s", key, len(codes), stale)

        results["indices"][key] = {
            "path": str(path),
            "count": len(codes),
            "source": source,
            "stale": stale,
            "tdx_count": len(tdx_codes),
            "csindex_count": len(cs_codes),
        }

    return results
