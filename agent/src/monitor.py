"""Real-time stock monitor — reliable multi-source data with technical signals."""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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
    updated_at: str = ""


# ── Technical indicators ────────────────────────────────────────────

def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        if d > 0: gains += d
        else: losses -= d
    if losses == 0: return 100.0
    rs = (gains / period) / (losses / period)
    return round(100.0 - 100.0 / (1.0 + rs), 1)


def _calc_macd(closes: list[float]) -> dict | None:
    if len(closes) < 26: return None
    def ema(data, n):
        k = 2.0 / (n + 1)
        out = [sum(data[:n]) / n]
        for v in data[n:]:
            out.append(v * k + out[-1] * (1 - k))
        return out
    e12, e26 = ema(closes, 12), ema(closes, 26)
    m = min(len(e12), len(e26))
    dif = [e12[-m + i] - e26[-m + i] for i in range(m)]
    dea = ema(dif, 9) if len(dif) >= 9 else dif
    bar = [2.0 * (dif[-len(dea) + i] - dea[i]) for i in range(len(dea))]
    return {"dif": round(dif[-1], 4), "dea": round(dea[-1], 4), "macd": round(bar[-1], 4)}


def _calc_ma(closes: list[float]) -> dict:
    return {
        "ma5": round(sum(closes[-5:]) / 5, 2) if len(closes) >= 5 else None,
        "ma10": round(sum(closes[-10:]) / 10, 2) if len(closes) >= 10 else None,
        "ma20": round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None,
        "ma60": round(sum(closes[-60:]) / 60, 2) if len(closes) >= 60 else None,
    }


def _detect_signals(closes: list[float], price: float) -> list[dict]:
    signals = []
    if len(closes) < 20: return signals
    ma = _calc_ma(closes)
    _prev = closes[-2] if len(closes) >= 2 else price
    # MA crossover
    if ma["ma5"] and ma["ma20"]:
        if _prev < ma["ma20"] and price > ma["ma20"]:
            signals.append({"type": "bullish", "message": "MA5上穿MA20 📈", "indicator": "金叉"})
        elif _prev > ma["ma20"] and price < ma["ma20"]:
            signals.append({"type": "bearish", "message": "MA5下穿MA20 📉", "indicator": "死叉"})
    # RSI
    rsi = _calc_rsi(closes)
    if rsi is not None:
        if rsi < 30: signals.append({"type": "bullish", "message": f"RSI超卖({rsi}) 📈", "indicator": "RSI"})
        elif rsi > 70: signals.append({"type": "bearish", "message": f"RSI超买({rsi}) 📉", "indicator": "RSI"})
    # MACD
    macd = _calc_macd(closes)
    if macd and macd["macd"] > 0 and macd["dif"] > macd["dea"]:
        signals.append({"type": "bullish", "message": "MACD金叉 📈", "indicator": "MACD"})
    elif macd and macd["macd"] < 0 and macd["dif"] < macd["dea"]:
        signals.append({"type": "bearish", "message": "MACD死叉 📉", "indicator": "MACD"})
    # Trend
    if ma["ma60"] and price < ma["ma60"] * 0.92:
        signals.append({"type": "bearish", "message": "跌破MA60 📉", "indicator": "趋势"})
    return signals[-5:]


# ── Data fetchers ────────────────────────────────────────────────────

def _fetch_yahoo_direct(symbol: str) -> tuple[float, float, list[float], float, str, float, float] | None:
    """Direct Yahoo Finance v8 API. Returns (price, change%, closes, volume, name, hi52, lo52)."""
    try:
        import requests
        syms = [symbol]
        if symbol.endswith(".HK"):
            code = symbol.replace(".HK", "")
            syms.append(f"{int(code):04d}.HK")
        for sym in set(syms):
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=6mo"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            if r.status_code != 200: continue
            data = r.json()
            result = data.get("chart", {}).get("result", [])
            if not result: continue
            meta = result[0].get("meta", {})
            ind = result[0].get("indicators", {})
            if not ind: continue
            quotes = ind.get("quote", [{}])[0]
            adj = ind.get("adjclose", [{}])[0].get("adjclose") or quotes.get("close") or []
            if not adj: continue
            closes = [float(v) for v in adj if v is not None]
            if len(closes) < 2: continue
            price = float(meta.get("regularMarketPrice", closes[-1]))
            prev = closes[-2]
            chg = round((price / prev - 1) * 100, 2)
            vol = float(quotes.get("volume", [0])[-1] or 0)
            name = str(meta.get("shortName") or meta.get("symbol") or symbol)
            hi = float(meta.get("fiftyTwoWeekHigh", 0))
            lo = float(meta.get("fiftyTwoWeekLow", 0))
            return price, chg, closes, vol, name, hi, lo
    except Exception as e:
        logger.debug("yahoo direct failed for %s: %s", symbol, e)
    return None


def _fetch_sina(symbol: str) -> tuple[float, float, list[float], str] | None:
    """Sina Finance for HK/A-shares. Returns (price, change%, closes, name)."""
    try:
        import requests
        code = symbol.replace(".HK", "").replace(".SZ", "").replace(".SH", "")
        if symbol.endswith(".HK"):
            quote_url = f"https://hq.sinajs.cn/list=hk{int(code):05d}"
            hist_url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=hk{int(code):05d}&scale=240&ma=no&datalen=60"
        elif symbol.endswith(".SZ"):
            quote_url = f"https://hq.sinajs.cn/list=sz{code}"
            hist_url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sz{code}&scale=240&ma=no&datalen=60"
        elif symbol.endswith(".SH"):
            quote_url = f"https://hq.sinajs.cn/list=sh{code}"
            hist_url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh{code}&scale=240&ma=no&datalen=60"
        else:
            return None

        headers = {"Referer": "https://finance.sina.com.cn"}
        # Quote
        qr = requests.get(quote_url, headers=headers, timeout=8)
        qr.encoding = "gbk"
        if qr.status_code != 200: return None
        m = re.search(r'"(.+)"', qr.text)
        if not m: return None
        fields = m.group(1).split(",")
        if len(fields) < 5: return None

        if symbol.endswith(".HK"):
            name = fields[1] if len(fields) > 1 else ""
            price = float(fields[6]) if fields[6] else 0
            prev_close = float(fields[3]) if fields[3] else price
        else:
            name = fields[0]
            price = float(fields[3]) if fields[3] else 0
            prev_close = float(fields[2]) if fields[2] else price
        chg = round((price / prev_close - 1) * 100, 2) if prev_close else 0

        # History
        closes: list[float] = []
        hr = requests.get(hist_url, headers=headers, timeout=8)
        if hr.status_code == 200:
            hist = hr.json()
            closes = [float(d["close"]) for d in hist if d.get("close")]

        return price, chg, closes, name
    except Exception as e:
        logger.debug("sina failed for %s: %s", symbol, e)
    return None


# ── Main fetch ───────────────────────────────────────────────────────

def fetch_quote(symbol: str) -> MonitorQuote:
    q = MonitorQuote(symbol=symbol)
    symbol = symbol.strip().upper()

    # 1. Yahoo Finance (best for US stocks)
    yh = _fetch_yahoo_direct(symbol)
    if yh:
        q.price, q.change_pct, closes, q.volume, q.name, q.high_52w, q.low_52w = yh
        if closes:
            q.signals = _detect_signals(closes, q.price)
            q.indicators = {"rsi": _calc_rsi(closes), "macd": _calc_macd(closes), "ma": _calc_ma(closes)}
        q.updated_at = datetime.now().isoformat()
        if q.price > 0:
            return q

    # 2. Sina Finance (best for HK/A-shares)
    si = _fetch_sina(symbol)
    if si:
        q.price, q.change_pct, closes, q.name = si
        if closes:
            q.signals = _detect_signals(closes, q.price)
            q.indicators = {"rsi": _calc_rsi(closes), "macd": _calc_macd(closes), "ma": _calc_ma(closes)}
        q.updated_at = datetime.now().isoformat()
        if q.price > 0:
            return q

    q.error = "无法获取数据，请检查代码并重试"
    return q


def fetch_quotes(symbols: list[str]) -> list[MonitorQuote]:
    results = []
    for sym in symbols:
        sym = sym.strip().upper()
        if sym:
            results.append(fetch_quote(sym))
    return results
