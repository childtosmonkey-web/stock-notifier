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
from news import fetch_ticker_news, analyze_with_gemini, save_report_to_github


def load_config() -> dict:
    with open(os.path.join(ROOT_DIR, "config.json")) as f:
        return json.load(f)


def main():
    import datetime, zoneinfo
    config = load_config()

    # スケジュール実行時（workflow_dispatch以外）は時刻チェック
    if os.environ.get("SCHEDULED_RUN") == "1":
        jst = zoneinfo.ZoneInfo("Asia/Tokyo")
        current_hour = datetime.datetime.now(jst).hour
        notify_hour = config.get("notify_hour", 8)
        if current_hour != notify_hour:
            print(f"現在 {current_hour} 時 / 通知設定 {notify_hour} 時 → スキップ")
            return

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

    # ニュース取得とAIレポート生成
    polygon_key = os.environ.get("POLYGON_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key and polygon_key and results:
        try:
            print("ニュースを取得中...")
            news_by_ticker: dict = {}
            for ticker in tickers:
                articles = fetch_ticker_news(ticker, polygon_key)
                news_by_ticker[ticker] = articles
                print(f"  {ticker}: {len(articles)}件のニュース取得")
                time.sleep(13)  # Polygon レート制限対策

            print("Gemini APIで分析中...")
            stocks_for_analysis = [r["stock"] for r in results]
            report_text = analyze_with_gemini(stocks_for_analysis, news_by_ticker)

            github_token = os.environ.get("GITHUB_TOKEN", "")
            github_username = os.environ.get("GITHUB_USERNAME", "childtosmonkey-web")
            save_report_to_github(report_text, tickers, github_token, github_username)
            print("レポートをGitHubに保存しました")
        except Exception as e:
            print(f"レポート生成エラー（通知は続行）: {e}", file=sys.stderr)
    else:
        print("GEMINI_API_KEY 未設定のためレポート生成をスキップ")

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
