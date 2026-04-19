# 通知する銘柄リスト（ティッカーシンボル）
TICKERS = ["AAPL", "NVDA"]

# チャートの表示期間（日数）
CHART_DAYS = 30

# 通知メッセージのフォーマット
MESSAGE_TEMPLATE = """{ticker}
現在値: ${price:.2f}
前日比: {change:+.2f} ({change_pct:+.2f}%)
"""
