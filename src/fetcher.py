"""株価データの取得（Polygon.io）"""

import os
import time
from datetime import date, timedelta
from itertools import islice
from polygon import RESTClient

# Polygon無料プランは5回/分。13秒間隔で全呼び出しを制御する
_POLYGON_MIN_INTERVAL = 13.0
_last_polygon_call: float = 0.0


def polygon_rate_limit() -> None:
    """Polygon APIコール前に呼ぶ。必要な待機時間だけスリープする。"""
    global _last_polygon_call
    wait = _POLYGON_MIN_INTERVAL - (time.time() - _last_polygon_call)
    if wait > 0:
        time.sleep(wait)
    _last_polygon_call = time.time()


def get_stock_data(ticker: str) -> dict:
    """指定したティッカーの株価データを返す。

    Returns:
        {
            "ticker": str,
            "price": float,       # 前日終値
            "prev_close": float,  # 前々日終値
            "change": float,      # 前日比（金額）
            "change_pct": float,  # 前日比（%）
            "date": str,          # データの日付
        }
    """
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        raise ValueError("POLYGON_API_KEY が設定されていません")

    client = RESTClient(api_key=api_key)

    # 直近5営業日分取得（週末・祝日対応）
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=7)

    polygon_rate_limit()
    aggs = list(islice(client.list_aggs(
        ticker=ticker,
        multiplier=1,
        timespan="day",
        from_=start.strftime("%Y-%m-%d"),
        to=end.strftime("%Y-%m-%d"),
        adjusted=True,
        sort="desc",
        limit=2,
    ), 2))

    if len(aggs) < 2:
        raise ValueError(f"{ticker}: データが取得できませんでした（銘柄コードを確認してください）")

    latest = aggs[0]
    prev = aggs[1]

    price = latest.close
    prev_close = prev.close
    change = price - prev_close
    change_pct = (change / prev_close) * 100

    return {
        "ticker": ticker,
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "date": str(latest.timestamp)[:10] if latest.timestamp else "",
    }


def get_ohlcv_for_chart(ticker: str, days: int = 30) -> list[dict]:
    """チャート用のOHLCVデータを返す。"""
    api_key = os.environ.get("POLYGON_API_KEY")
    client = RESTClient(api_key=api_key)

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days + 10)  # 週末・祝日の余裕

    polygon_rate_limit()
    aggs = list(islice(client.list_aggs(
        ticker=ticker,
        multiplier=1,
        timespan="day",
        from_=start.strftime("%Y-%m-%d"),
        to=end.strftime("%Y-%m-%d"),
        adjusted=True,
        sort="asc",
        limit=days + 10,
    ), days + 10))

    return [
        {
            "timestamp": a.timestamp,
            "open": a.open,
            "high": a.high,
            "low": a.low,
            "close": a.close,
            "volume": a.volume,
        }
        for a in aggs[-days:]
    ]
