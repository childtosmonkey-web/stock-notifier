"""メインエントリーポイント"""

import sys
import os
import json
import time
import base64
import requests

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(override=True)

from fetcher import get_stock_data, get_ohlcv_for_chart
from chart import generate_chart
from notifier import upload_to_github
from web_push import send_combined_push
from news import fetch_ticker_news, analyze_with_groq, save_report_to_github


def load_config() -> dict:
    with open(os.path.join(ROOT_DIR, "config.json")) as f:
        return json.load(f)


def save_last_notified(today: str) -> None:
    """config.jsonのlast_notified_dateをGitHub APIで更新（二重通知防止）"""
    github_token = os.environ.get("GITHUB_TOKEN", "")
    github_username = os.environ.get("GITHUB_USERNAME", "childtosmonkey-web")
    api_url = f"https://api.github.com/repos/{github_username}/stock-notifier/contents/config.json"
    headers = {"Authorization": f"token {github_token}"}

    r = requests.get(api_url, headers=headers, timeout=10)
    r.raise_for_status()
    body = r.json()
    config = json.loads(base64.b64decode(body["content"]).decode())
    config["last_notified_date"] = today
    content = base64.b64encode(json.dumps(config, indent=2, ensure_ascii=False).encode()).decode()
    requests.put(api_url, headers=headers,
                 json={"message": "Update last_notified_date", "content": content, "sha": body["sha"]},
                 timeout=30).raise_for_status()


def main():
    import datetime, zoneinfo
    config = load_config()

    # スケジュール実行時（workflow_dispatch以外）は時刻チェック
    jst = zoneinfo.ZoneInfo("Asia/Tokyo")
    now_jst = datetime.datetime.now(jst)
    today_str = now_jst.strftime("%Y-%m-%d")

    if os.environ.get("SCHEDULED_RUN") == "1":
        # 今日すでに通知済みなら二重送信しない
        if config.get("last_notified_date") == today_str:
            print(f"本日({today_str})はすでに通知済み → スキップ")
            return

        # GitHub Actionsのcron遅延対策：±1時間の範囲で許容
        current_hour = now_jst.hour
        notify_hour = config.get("notify_hour", 8)
        if abs(current_hour - notify_hour) > 1:
            print(f"現在 {current_hour} 時 / 通知設定 {notify_hour} 時（±1時間範囲外） → スキップ")
            return
        print(f"現在 {current_hour} 時 / 通知設定 {notify_hour} 時 → 実行")

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
        except Exception as e:
            print(f"  {ticker}: 株価取得エラー - {e}", file=sys.stderr)
            continue

        chart_url = None
        try:
            ohlcv = get_ohlcv_for_chart(ticker, days=chart_days)
            chart_path = generate_chart(ticker, ohlcv)
            chart_url = upload_to_github(chart_path)
            print(f"  {ticker}: チャート生成・アップロード完了")
        except Exception as e:
            print(f"  {ticker}: チャートエラー（通知は続行） - {e}", file=sys.stderr)

        results.append({"stock": stock, "chart_url": chart_url})

    # ニュース取得とAIレポート生成
    polygon_key = os.environ.get("POLYGON_API_KEY", "")
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key and polygon_key and results:
        try:
            print("ニュースを取得中...")
            news_by_ticker: dict = {}
            for ticker in tickers:
                articles = fetch_ticker_news(ticker, polygon_key)
                news_by_ticker[ticker] = articles
                print(f"  {ticker}: {len(articles)}件のニュース取得")

            print("Groq APIで分析中...")
            stocks_for_analysis = [r["stock"] for r in results]
            report_text = analyze_with_groq(stocks_for_analysis, news_by_ticker)

            github_token = os.environ.get("GITHUB_TOKEN", "")
            github_username = os.environ.get("GITHUB_USERNAME", "childtosmonkey-web")
            save_report_to_github(report_text, tickers, github_token, github_username)
            print("レポートをGitHubに保存しました")
        except Exception as e:
            print(f"レポート生成エラー（通知は続行）: {e}", file=sys.stderr)
    else:
        print("GROQ_API_KEY 未設定のためレポート生成をスキップ")

    if subscription and results:
        try:
            stocks = [r["stock"] for r in results]
            send_combined_push(subscription, stocks)
            tickers_str = ", ".join(s["ticker"] for s in stocks)
            print(f"Web Push送信完了: {tickers_str}")
            # 送信成功後に今日の通知済みフラグを保存
            if os.environ.get("SCHEDULED_RUN") == "1":
                try:
                    save_last_notified(today_str)
                    print("通知済み日付を保存しました")
                except Exception as e:
                    print(f"通知済み日付の保存エラー: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Push送信エラー: {e}", file=sys.stderr)

    print("完了")


if __name__ == "__main__":
    main()
