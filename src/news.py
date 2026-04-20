"""ニュース取得とAI分析レポート生成"""

import os
import json
import base64
import requests
from datetime import datetime, timedelta

GITHUB_REPO = "stock-notifier"
REPORT_PATH = "daily_report.json"


def fetch_ticker_news(ticker: str, api_key: str, hours: int = 24) -> list[dict]:
    """Polygon APIから指定銘柄の直近ニュースを取得"""
    from_dt = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        r = requests.get(
            "https://api.polygon.io/v2/reference/news",
            params={
                "ticker": ticker,
                "published_utc.gte": from_dt,
                "limit": 8,
                "order": "desc",
                "sort": "published_utc",
                "apiKey": api_key,
            },
            timeout=10,
        )
        if r.ok:
            return r.json().get("results", [])
    except Exception:
        pass
    return []


def analyze_with_claude(stocks: list[dict], news_by_ticker: dict[str, list]) -> str:
    """Claude APIで株価とニュースを分析・要約してレポートを生成"""
    try:
        import anthropic
    except ImportError:
        return "anthropicパッケージが未インストールです"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "ANTHROPIC_API_KEY が未設定です"

    client = anthropic.Anthropic(api_key=api_key)

    # 株価サマリー
    stocks_lines = []
    for s in stocks:
        if s.get("price") is None:
            continue
        direction = "▲" if s["change_pct"] >= 0 else "▼"
        stocks_lines.append(
            f"- {s['ticker']}: ${s['price']:.2f}  "
            f"{direction}{abs(s['change_pct']):.2f}%（前日比 {s['change']:+.2f}）"
        )
    stocks_text = "\n".join(stocks_lines) or "データなし"

    # ニュースサマリー
    news_sections = []
    for ticker, articles in news_by_ticker.items():
        if not articles:
            news_sections.append(f"**{ticker}**: 直近24時間のニュースなし")
            continue
        lines = [f"**{ticker}**"]
        for a in articles[:6]:
            title = a.get("title", "")
            desc = (a.get("description") or "")[:250]
            pub = (a.get("published_utc") or "")[:10]
            lines.append(f"- [{pub}] {title}")
            if desc:
                lines.append(f"  {desc}")
        news_sections.append("\n".join(lines))
    news_text = "\n\n".join(news_sections) or "ニュースなし"

    prompt = f"""あなたは株式市場アナリストです。以下の株価データと関連ニュースを基に、日本語でデイリーレポートを作成してください。

## 本日の株価
{stocks_text}

## 関連ニュース（直近24時間）
{news_text}

---

以下の構成でレポートを作成してください（合計3〜5分で読める分量）：

### 📊 本日のサマリー
全体的な市場動向と注目点を3文程度で。

### 📈 銘柄別分析
各銘柄について：
- 株価変動の主な要因（ニュースと具体的に結びつけて説明）
- 特記事項（決算、製品発表、規制動向など）

### 🔍 今後の注目ポイント
今後数日間で注目すべきイベントや指標を2〜3点。

株価変動とニュースの因果関係を具体的に説明してください。ニュースがない銘柄は市場全体の動向から推察してください。"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def save_report_to_github(
    report_text: str,
    tickers: list[str],
    github_token: str,
    github_username: str,
) -> None:
    """レポートをGitHubのdaily_report.jsonに保存"""
    headers = {"Authorization": f"token {github_token}"}
    api_url = (
        f"https://api.github.com/repos/{github_username}/{GITHUB_REPO}"
        f"/contents/{REPORT_PATH}"
    )

    data = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "tickers": tickers,
        "report": report_text,
    }
    content = base64.b64encode(
        json.dumps(data, indent=2, ensure_ascii=False).encode()
    ).decode()
    payload = {"message": "Update daily_report.json", "content": content}

    # 既存ファイルの SHA を取得（PUT に必要）
    r = requests.get(api_url, headers=headers, timeout=10)
    if r.ok:
        payload["sha"] = r.json()["sha"]

    r = requests.put(api_url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
