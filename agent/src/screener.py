"""Multi-factor A-share screener — heat rank pool + monitor-based scoring."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.monitor import fetch_quote

logger = logging.getLogger(__name__)

WEIGHTS = {"momentum": 0.25, "technical": 0.20, "volume": 0.10, "trend": 0.10,
           "catalyst": 0.10, "industry": 0.10, "news_sentiment": 0.10, "value": 0.05}

@dataclass
class FactorScores:
    momentum: float = 5.0; technical: float = 5.0; volume: float = 5.0
    trend: float = 5.0; catalyst: float = 5.0; industry: float = 5.0
    news_sentiment: float = 5.0; value: float = 5.0

    @property
    def total(self) -> float:
        return (self.momentum * 0.25 + self.technical * 0.20 + self.volume * 0.10
                + self.trend * 0.10 + self.catalyst * 0.10 + self.industry * 0.10
                + self.news_sentiment * 0.10 + self.value * 0.05) * 10

@dataclass
class StockScore:
    symbol: str; name: str = ""; price: float = 0.0; change_pct: float = 0.0
    pe: float = 0.0; pb: float = 0.0; roe: float = 0.0; market_cap: float = 0.0
    total_score: float = 0.0
    factors: FactorScores = field(default_factory=FactorScores)
    signals: list[str] = field(default_factory=list)


def _score_one(symbol: str) -> StockScore | None:
    """Score a single stock using monitor data."""
    q = fetch_quote(symbol)
    if q.error or q.price <= 0 or not q.indicators:
        return None

    ind = q.indicators
    ma = ind.get("ma", {}) or {}
    rsi = ind.get("rsi")
    macd = ind.get("macd", {}) or {}
    price = q.price
    chg = q.change_pct
    s = StockScore(symbol=symbol, name=q.name, price=round(price, 2),
                   change_pct=round(chg, 2))

    # Momentum
    mom = 5.0
    if ma.get("ma5") and ma.get("ma20"):
        if price > ma["ma5"] > ma["ma20"]: mom = 9
        elif price > ma["ma20"]: mom = 7
        elif price > ma.get("ma60", price): mom = 5
        else: mom = 3
    s.factors.momentum = mom

    # Technical
    tech = 5.0
    if rsi is not None:
        if 40 <= rsi <= 60: tech += 2
        elif rsi < 30: tech += 3
        elif rsi > 70: tech -= 1
    if macd.get("macd") and macd["macd"] > 0: tech += 2
    if macd.get("dif") and macd.get("dea") and macd["dif"] > macd["dea"]: tech += 1
    if ma.get("ma5") and ma.get("ma20") and price > ma["ma5"] > ma["ma20"]: tech += 1
    s.factors.technical = max(0, min(10, tech))

    # Volume
    spread = abs(price - ma.get("ma20", price)) / price * 100 if ma.get("ma20") else 2
    s.factors.volume = min(10, max(2, 4 + spread))

    # Trend
    trend = 5.0
    if ma.get("ma5") and ma.get("ma20") and price > ma["ma5"] > ma["ma20"]: trend = 8
    elif ma.get("ma20") and price > ma["ma20"]: trend = 6
    elif ma.get("ma20") and price < ma["ma20"]: trend = 3
    s.factors.trend = trend

    # PE from yfinance (optional)
    pe = 0.0; pb = 0.0; mv = 0.0
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        pe = float(info.get("trailingPE") or info.get("forwardPE") or 0)
        pb = float(info.get("priceToBook") or 0)
        mv = float(info.get("marketCap") or 0)
    except Exception:
        pass
    s.pe = pe; s.pb = pb; s.market_cap = mv

    # Catalyst
    cat = 5.0
    if 0 < pe < 15: cat += 2
    elif 0 < pe < 25: cat += 1
    if rsi and rsi < 35: cat += 2
    s.factors.catalyst = max(0, min(10, cat))

    # Value
    v = 5.0
    if 0 < pe < 15: v += 2
    elif 0 < pe < 25: v += 1
    if 0 < pb < 1.5: v += 1
    s.factors.value = max(0, min(10, v))

    s.factors.industry = 5.0
    s.factors.news_sentiment = 5.0
    s.total_score = round(s.factors.total, 1)

    if s.factors.momentum >= 7: s.signals.append("强动量")
    if s.factors.technical >= 7: s.signals.append("技术突破")
    if rsi and rsi < 35: s.signals.append("RSI超卖")
    if abs(chg) > 3: s.signals.append(f"{'+' if chg>0 else ''}{chg:.1f}%")
    return s


def screen(universe: str = "hk", top_n: int = 6, symbols: list[str] | None = None) -> list[StockScore]:
    stocks = symbols if symbols else []
    if not stocks:
        return []

    scores: list[StockScore] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_score_one, s): s for s in stocks}
        for fut in as_completed(futures, timeout=60):
            try:
                r = fut.result(timeout=12)
                if r: scores.append(r)
            except Exception:
                pass

    scores.sort(key=lambda x: x.total_score, reverse=True)
    return scores[:top_n]
