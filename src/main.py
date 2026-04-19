"""メインエントリーポイント"""

import sys
import os
import time

# プロジェクトルートをPATHに追加（config.py を import するため）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

from config import TICKERS, CHART_DAYS
from fetcher import get_stock_data, get_ohlcv_for_chart
from chart import generate_chart
from notifier import send_stock_notification


def main():
    print(f"株価通知を開始します: {TICKERS}")

    for ticker in TICKERS:
        try:
            print(f"  {ticker}: データ取得中...")
            stock = get_stock_data(ticker)
            print(f"  {ticker}: ${stock['price']:.2f} ({stock['change_pct']:+.2f}%)")

            ohlcv = get_ohlcv_for_chart(ticker, days=CHART_DAYS)
            chart_path = generate_chart(ticker, ohlcv)
            print(f"  {ticker}: チャート生成完了 -> {chart_path}")

            send_stock_notification(stock, chart_path)
            print(f"  {ticker}: LINE通知送信完了")
            time.sleep(15)  # レート制限対策（無料プラン: 5回/分）

        except Exception as e:
            print(f"  {ticker}: エラー - {e}", file=sys.stderr)

    print("完了")


if __name__ == "__main__":
    main()
