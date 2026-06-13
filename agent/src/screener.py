"""Multi-factor stock screener for daily/weekly picks."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.monitor import fetch_quote, _calc_rsi, _calc_macd, _calc_ma

logger = logging.getLogger(__name__)

# ── Default universes ────────────────────────────────────────────────

HK_TOP = [
    "00700.HK", "09988.HK", "00941.HK", "00388.HK", "01299.HK",
    "00005.HK", "02318.HK", "00939.HK", "01398.HK", "03988.HK",
    "01810.HK", "02382.HK", "01093.HK", "02628.HK", "01109.HK",
    "06869.HK", "02015.HK", "09618.HK", "09888.HK", "02020.HK",
    "00175.HK", "02269.HK", "01211.HK", "09633.HK", "06160.HK",
    "09999.HK", "01024.HK", "03690.HK", "09961.HK", "00669.HK",
]

CSI300_TOP = [
    "600519.SH", "000858.SZ", "601318.SH", "000333.SZ", "600036.SH",
    "601166.SH", "000002.SZ", "600900.SH", "601012.SH", "600030.SH",
    "000001.SZ", "002415.SZ", "601398.SH", "600276.SH", "000651.SZ",
    "300750.SZ", "603259.SH", "000725.SZ", "002714.SZ", "601888.SH",
    "600809.SH", "000568.SZ", "002475.SZ", "300059.SZ", "601899.SH",
    "603288.SH", "000063.SZ", "002304.SZ", "600585.SH", "000895.SZ",
]

US_TOP = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM",
    "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC",
    "XOM", "NFLX", "ADBE", "CRM", "AMD", "INTC", "PYPL", "COST",
]


@dataclass
class StockScore:
    symbol: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    total_score: float = 0.0
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volume_score: float = 0.0
    rsi_score: float = 0.0
    macd_score: float = 0.0
    signals: list[str] = field(default_factory=list)
    error: str = ""


def _score_stock(symbol: str) -> StockScore:
    """Calculate multi-factor score for a single stock."""
    s = StockScore(symbol=symbol)
    q = fetch_quote(symbol)
    if q.error:
        s.error = q.error
        return s

    s.name = q.name
    s.price = q.price
    s.change_pct = q.change_pct

    ind = q.indicators or {}
    ma = ind.get("ma", {}) or {}
    rsi = ind.get("rsi")
    macd = ind.get("macd", {}) or {}

    # 1. Trend score (0-25): MA alignment
    trend = 0
    if ma.get("ma5") and ma.get("ma20"):
        # MA5 > MA20 = upward trend
        if ma["ma5"] > ma["ma20"]:
            trend += 10
        if ma.get("ma10") and ma["ma10"] > ma.get("ma20", 0):
            trend += 5
        if ma.get("ma20") and ma.get("ma60") and ma["ma20"] > ma["ma60"]:
            trend += 5
        # Price above all MAs
        if s.price > ma["ma5"] and s.price > ma["ma20"]:
            trend += 5
    s.trend_score = trend

    # 2. Momentum score (0-25): recent returns
    momentum = 0
    if s.change_pct > 5:
        momentum = 25
    elif s.change_pct > 3:
        momentum = 20
    elif s.change_pct > 1:
        momentum = 15
    elif s.change_pct > 0:
        momentum = 10
    elif s.change_pct > -1:
        momentum = 5
    else:
        momentum = 0
    s.momentum_score = momentum

    # 3. Volume score (0-20): volume surge (approximate with change_pct direction)
    vol = 10  # neutral
    if abs(s.change_pct) > 2:
        vol = min(20, 10 + abs(s.change_pct))
    s.volume_score = vol

    # 4. RSI score (0-15)
    rsi_s = 7
    if rsi is not None:
        if 40 <= rsi <= 60:
            rsi_s = 12  # healthy range
        elif 30 <= rsi <= 70:
            rsi_s = 8
        elif rsi < 30:
            rsi_s = 15  # oversold = potential reversal up
        else:
            rsi_s = 3  # overbought
    s.rsi_score = rsi_s

    # 5. MACD score (0-15)
    macd_s = 7
    if macd.get("macd") is not None:
        if macd["macd"] > 0:
            macd_s = 12
        elif macd["macd"] < -0.5:
            macd_s = 3
        else:
            macd_s = 8
    s.macd_score = macd_s

    s.total_score = s.trend_score + s.momentum_score + s.volume_score + s.rsi_score + s.macd_score

    # Collect signals
    for sig in q.signals:
        s.signals.append(sig.get("message", ""))

    return s


def screen(universe: list[str], top_n: int = 10) -> list[StockScore]:
    """Screen a universe of stocks and return top picks."""
    scores = []
    for sym in universe:
        sc = _score_stock(sym)
        if not sc.error:
            scores.append(sc)
    scores.sort(key=lambda x: x.total_score, reverse=True)
    return scores[:top_n]


def get_universe(name: str) -> list[str]:
    """Get a predefined stock universe."""
    name = name.lower()
    if name in ("hk", "港股", "hk_top"):
        return HK_TOP
    if name in ("csi300", "沪深300", "a股"):
        return CSI300_TOP
    if name in ("us", "美股", "us_top"):
        return US_TOP
    return []
