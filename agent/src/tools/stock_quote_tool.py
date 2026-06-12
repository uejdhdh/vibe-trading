"""Stock quote tool: real-time stock data with technical indicators via Yahoo+Sina."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool


class StockQuoteTool(BaseTool):
    """Get real-time stock quotes with price, change, and technical indicators."""

    name = "get_stock_quote"

    @classmethod
    def check_available(cls) -> bool:
        return True

    description = (
        "Get real-time stock quote with current price, daily change %, "
        "52-week high/low, volume, and computed technical indicators "
        "(MA5/10/20/60, RSI-14, MACD) plus detected signals "
        "(golden cross, death cross, overbought/oversold). "
        "Supports HK stocks (00700.HK), A-shares (600519.SH, 000001.SZ), "
        "and US stocks (AAPL, TSLA). "
        "Use this whenever you need accurate, up-to-date price data."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol: HK (00700.HK), A-share (600519.SH, 000001.SZ), US (AAPL)",
            },
        },
        "required": ["symbol"],
    }
    repeatable = True

    def execute(self, **kwargs: Any) -> str:
        symbol = str(kwargs.get("symbol", "")).strip().upper()
        if not symbol:
            return json.dumps({"status": "error", "error": "symbol is required"}, ensure_ascii=False)

        from src.monitor import fetch_quote

        try:
            q = fetch_quote(symbol)
            if q.error and q.price == 0:
                return json.dumps({"status": "error", "symbol": symbol, "error": q.error}, ensure_ascii=False)

            return json.dumps(
                {
                    "status": "ok",
                    "symbol": q.symbol,
                    "name": q.name,
                    "price": q.price,
                    "change_pct": q.change_pct,
                    "high_52w": q.high_52w,
                    "low_52w": q.low_52w,
                    "volume": q.volume,
                    "indicators": q.indicators,
                    "signals": q.signals,
                    "source_note": "Yahoo Finance / Sina Finance real-time data",
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:
            return json.dumps({"status": "error", "symbol": symbol, "error": str(exc)}, ensure_ascii=False)
