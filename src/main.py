"""メインエントリーポイント"""

import sys
import os
import json
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(override=True)

from fetcher import get_stock_data, get_ohlcv_for_chart
from chart import generate_chart
from notifier import upload_to_github
from web_push import send_stock_push


def load_config() -> dict:
    with open(os.path.join(ROOT_DIR, "config.json")) as f:
        return json.load(f)


def main():
    config = load_config()
    tickers = config["tickers"]
    chart_days = config.get("chart_days", 30)
    subscription = config.get("push_subscription")

    print(f"株価通知を開始します: {tickers}")

    if not subscription:
        print("push_subscription 未設定のため通知をスキップします", file=sys.stderr)

    results = []
    for ticker in tickers:
        try:
            print(f"  {ticker}: データ取得中...")
            stock = get_stock_data(ticker)
            print(f"  {ticker}: ${stock['price']:.2f} ({stock['change_pct']:+.2f}%)")

            ohlcv = get_ohlcv_for_chart(ticker, days=chart_days)
            chart_path = generate_chart(ticker, ohlcv)
            chart_url = upload_to_github(chart_path)
            print(f"  {ticker}: チャート生成・アップロード完了")

            results.append({"stock": stock, "chart_url": chart_url})
            time.sleep(15)  # レート制限対策（無料プラン: 5回/分）

        except Exception as e:
            print(f"  {ticker}: エラー - {e}", file=sys.stderr)

    if subscription and results:
        for r in results:
            try:
                send_stock_push(subscription, r["stock"], r["chart_url"])
                print(f"  {r['stock']['ticker']}: Web Push送信完了")
            except Exception as e:
                print(f"  {r['stock']['ticker']}: Push送信エラー - {e}", file=sys.stderr)

    print("完了")


if __name__ == "__main__":
    main()
