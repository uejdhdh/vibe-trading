"""Real-time stock monitor with technical signals."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class MonitorQuote:
    symbol: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    high_52w: float = 0.0
    low_52w: float = 0.0
    volume: float = 0.0
    signals: list[dict] = field(default_factory=list)
    indicators: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - 100.0 / (1.0 + rs), 1)


def _calc_macd(closes: list[float]) -> dict | None:
    if len(closes) < 26:
        return None

    def ema(data: list[float], n: int) -> list[float]:
        k = 2.0 / (n + 1)
        out = [sum(data[:n]) / n]
        for v in data[n:]:
            out.append(v * k + out[-1] * (1 - k))
        return out

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    min_len = min(len(ema12), len(ema26))
    dif = [ema12[-min_len + i] - ema26[-min_len + i] for i in range(min_len)]
    dea = ema(dif, 9) if len(dif) >= 9 else dif
    macd_bar = [2.0 * (dif[-len(dea) + i] - dea[i]) for i in range(len(dea))]
    return {
        "dif": round(dif[-1], 4),
        "dea": round(dea[-1], 4),
        "macd": round(macd_bar[-1], 4),
    }


def _calc_ma(closes: list[float]) -> dict:
    ma5 = round(sum(closes[-5:]) / 5, 2) if len(closes) >= 5 else None
    ma10 = round(sum(closes[-10:]) / 10, 2) if len(closes) >= 10 else None
    ma20 = round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None
    ma60 = round(sum(closes[-60:]) / 60, 2) if len(closes) >= 60 else None
    return {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60}


def _detect_signals(closes: list[float], price: float) -> list[dict]:
    signals: list[dict] = []
    if len(closes) < 60:
        return signals

    ma = _calc_ma(closes)
    # MA crossover: MA5 crosses MA20
    if ma["ma5"] and ma["ma20"]:
        if closes[-2] <= ma["ma20"] and price > ma["ma20"]:
            signals.append({"type": "bullish", "message": "MA5 上穿 MA20 📈", "indicator": "MA金叉"})
        elif closes[-2] >= ma["ma20"] and price < ma["ma20"]:
            signals.append({"type": "bearish", "message": "MA5 下穿 MA20 📉", "indicator": "MA死叉"})

    # RSI
    rsi = _calc_rsi(closes)
    if rsi is not None:
        if rsi < 30:
            signals.append({"type": "bullish", "message": f"RSI 超卖 ({rsi}) 📈", "indicator": "RSI"})
        elif rsi > 70:
            signals.append({"type": "bearish", "message": f"RSI 超买 ({rsi}) 📉", "indicator": "RSI"})

    # MACD
    macd = _calc_macd(closes)
    if macd:
        if macd["dif"] > macd["dea"] and macd["macd"] > 0:
            signals.append({"type": "bullish", "message": "MACD 金叉 📈", "indicator": "MACD"})
        elif macd["dif"] < macd["dea"] and macd["macd"] < 0:
            signals.append({"type": "bearish", "message": "MACD 死叉 📉", "indicator": "MACD"})

    # Price relative to MA60
    if ma["ma60"] and price < ma["ma60"] * 0.95:
        signals.append({"type": "bearish", "message": "股价低于 MA60 📉", "indicator": "趋势偏弱"})

    return signals[-4:]  # limit signals


def fetch_quote(symbol: str) -> MonitorQuote:
    """Fetch a single stock quote with signals."""
    quote = MonitorQuote(symbol=symbol)
    closes: list[float] = []

    # Try yfinance with session retry
    try:
        import yfinance as yf
        import requests
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        t = yf.Ticker(symbol, session=session)
        info = t.info if t.info else {}
        hist = t.history(period="3mo")
        if hist is not None and not hist.empty:
            closes = hist["Close"].tolist()
            if closes:
                quote.price = round(float(closes[-1]), 2)
                quote.change_pct = round((closes[-1] / closes[-2] - 1) * 100, 2) if len(closes) >= 2 else 0
                quote.volume = float(hist["Volume"].iloc[-1]) if "Volume" in hist else 0
        if info:
            quote.name = str(info.get("shortName") or info.get("longName") or "")
            quote.high_52w = float(info.get("fiftyTwoWeekHigh") or 0)
            quote.low_52w = float(info.get("fiftyTwoWeekLow") or 0)
    except Exception as e:
        logger.debug("yfinance fetch failed for %s: %s", symbol, e)

    # Fallback: akshare
    if not closes:
        try:
            import akshare as ak
            df = None
            if symbol.endswith(".HK"):
                code = symbol.replace(".HK", "")
                try:
                    df = ak.stock_hk_hist(symbol=code, period="daily", adjust="qfq")
                except Exception:
                    df = ak.stock_hk_hist(symbol=code, period="daily", adjust="")
            elif symbol.endswith((".SZ", ".SH")):
                code = symbol.replace(".SZ", "").replace(".SH", "")
                try:
                    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
                except Exception:
                    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="")
            else:
                # Try US stock
                try:
                    df = ak.stock_us_hist(symbol=symbol, period="daily", adjust="qfq")
                except Exception:
                    df = ak.stock_us_hist(symbol=symbol, period="daily", adjust="")
            if df is not None and not df.empty:
                col = None
                for c in ["收盘", "close", "Close"]:
                    if c in df.columns:
                        col = c
                        break
                if col is None:
                    col = df.columns[3] if len(df.columns) > 3 else df.columns[-1]
                closes_col = df[col].tolist()
                closes = [float(v) for v in closes_col if v and str(v) != "nan"]
                if closes:
                    quote.price = round(float(closes[-1]), 2)
                    if len(closes) >= 2:
                        quote.change_pct = round((closes[-1] / closes[-2] - 1) * 100, 2)
        except Exception as e:
            quote.error = f"数据获取失败: {str(e)[:150]}"
            return quote

    # Fallback: ddgs web search for price
    if not closes:
        try:
            from ddgs import DDGS
            with DDGS() as ddg:
                results = list(ddg.text(f"{symbol} stock price today", max_results=3))
                for r in results:
                    quote.name = r.get("title", "")[:100]
                    body = r.get("body", "")
                    if "$" in body or "¥" in body or "HK$" in body:
                        import re
                        prices = re.findall(r'[\$¥HK\$\s]*(\d+\.?\d*)', body)
                        if prices:
                            quote.price = float(prices[0])
                            quote.change_pct = 0
                        break
            if quote.price > 0:
                quote.error = "仅获取到价格（来自搜索引擎）"
                return quote
        except Exception:
            pass

    if not closes:
        quote.error = "无法获取数据，请稍后重试。yfinance 和 akshare 均不可用。"
        return quote

    quote.signals = _detect_signals(closes, quote.price)
    quote.indicators = {
        "rsi": _calc_rsi(closes),
        "macd": _calc_macd(closes),
        "ma": _calc_ma(closes),
    }
    return quote


def fetch_quotes(symbols: list[str]) -> list[MonitorQuote]:
    """Fetch quotes for multiple symbols."""
    results: list[MonitorQuote] = []
    for sym in symbols:
        sym = sym.strip().upper()
        if sym:
            results.append(fetch_quote(sym))
    return results
