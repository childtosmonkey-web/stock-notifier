"""ニュース取得とAI分析レポート生成"""

import os
import json
import base64
import requests
from datetime import datetime, timedelta

GITHUB_REPO = "stock-notifier"
REPORT_PATH = "daily_report.json"


def _fetch_from_polygon(ticker: str, api_key: str, hours: int = 24) -> list[dict]:
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


def _fetch_from_yfinance(ticker: str, hours: int = 24) -> list[dict]:
    """yfinance経由でYahoo Financeのニュースを取得（Reuters, AP等を含む）"""
    try:
        import yfinance as yf
        from datetime import timezone
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        articles = yf.Ticker(ticker).news or []
        result = []
        for a in articles:
            pub_ts = a.get("providerPublishTime", 0)
            pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
            if pub_dt < cutoff:
                continue
            result.append({
                "title": a.get("title", ""),
                "description": a.get("summary", ""),
                "published_utc": pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "publisher": a.get("publisher", ""),
            })
        return result
    except Exception:
        return []


def _fetch_from_finnhub(ticker: str, hours: int = 24) -> list[dict]:
    """Finnhub APIから指定銘柄のニュースを取得（Bloomberg, Reuters, Dow Jones等）"""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return []
    try:
        from datetime import timezone
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(hours=hours)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")
        r = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": ticker, "from": from_date, "to": to_date, "token": api_key},
            timeout=10,
        )
        if not r.ok:
            return []
        result = []
        cutoff = now - timedelta(hours=hours)
        for a in r.json():
            pub_dt = datetime.fromtimestamp(a.get("datetime", 0), tz=timezone.utc)
            if pub_dt < cutoff:
                continue
            result.append({
                "title": a.get("headline", ""),
                "description": a.get("summary", ""),
                "published_utc": pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "publisher": a.get("source", ""),
            })
        return result
    except Exception:
        return []


def fetch_ticker_news(ticker: str, api_key: str, hours: int = 24) -> list[dict]:
    """Polygon + yfinance + Finnhubから指定銘柄の直近ニュースを取得（結合・重複除去）"""
    polygon = _fetch_from_polygon(ticker, api_key, hours)
    yf_news = _fetch_from_yfinance(ticker, hours)
    finnhub = _fetch_from_finnhub(ticker, hours)

    seen = set()
    combined = []
    for a in polygon + yf_news + finnhub:
        title = a.get("title", "").strip()
        if title and title not in seen:
            seen.add(title)
            combined.append(a)

    combined.sort(key=lambda x: x.get("published_utc", ""), reverse=True)
    return combined[:15]


_SIGNIFICANT_MOVE_PCT = 2.0


def analyze_with_groq(stocks: list[dict], news_by_ticker: dict[str, list]) -> str:
    """Groq APIで株価とニュースを分析・要約してレポートを生成"""
    try:
        from groq import Groq
    except ImportError:
        return "groqパッケージが未インストールです"

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "GROQ_API_KEY が未設定です"

    client = Groq(api_key=api_key)

    # 株価テーブル（数値改ざん防止のため明示的に構造化）
    stock_rows = []
    significant_tickers = []
    for s in stocks:
        if s.get("price") is None:
            continue
        direction = "▲" if s["change_pct"] >= 0 else "▼"
        is_significant = abs(s["change_pct"]) >= _SIGNIFICANT_MOVE_PCT
        flag = "★要分析" if is_significant else "軽微"
        stock_rows.append(
            f"| {s['ticker']} | ${s['price']:.2f} | {direction}{abs(s['change_pct']):.2f}% | {flag} |"
        )
        if is_significant:
            significant_tickers.append(s["ticker"])

    stock_table = (
        "| ティッカー | 終値 | 前日比 | 判定 |\n"
        "|---|---|---|---|\n"
        + "\n".join(stock_rows)
    )
    significant_str = "、".join(significant_tickers) if significant_tickers else "なし"

    # ニュース（大きな変動銘柄は多め、軽微は少なく）
    news_sections = []
    for ticker, articles in news_by_ticker.items():
        s = next((x for x in stocks if x["ticker"] == ticker), None)
        is_significant = s is not None and abs(s.get("change_pct", 0)) >= _SIGNIFICANT_MOVE_PCT
        limit = 8 if is_significant else 3

        if not articles:
            news_sections.append(f"**{ticker}**: ニュースなし")
            continue
        label = "★大きな変動あり" if is_significant else "軽微"
        lines = [f"**{ticker}**（{label}）"]
        for a in articles[:limit]:
            title = a.get("title", "")
            desc = (a.get("description") or "")[:200]
            pub = (a.get("published_utc") or "")[:16].replace("T", " ")
            publisher = a.get("publisher", "")
            line = f"- [{pub}]" + (f" ({publisher})" if publisher else "") + f" {title}"
            lines.append(line)
            if desc:
                lines.append(f"  → {desc}")
        news_sections.append("\n".join(lines))
    news_text = "\n\n".join(news_sections) or "ニュースなし"

    prompt = f"""あなたは株式市場アナリストです。以下のルールを厳守して日本語でレポートを作成してください。

## ⚠️ 厳守ルール
1. 株価・変動率は下記テーブルの数値のみを使用すること。絶対に変更・推測しないこと
2. ★要分析の銘柄（大きな変動）を優先して分析すること
3. 値動きの原因は提供されたニュースのみから説明すること
4. 該当ニュースが見つからない場合は「原因不明（関連ニュースなし）」と明記すること
5. 推測・一般論・中長期の話は含めないこと

## 本日の株価データ（この数値は変更禁止）
{stock_table}
大きな変動（±{_SIGNIFICANT_MOVE_PCT}%以上）: {significant_str}

## 直近24時間のニュース
{news_text}

---

### 📊 本日のサマリー（3文以内）
大きな変動があった銘柄を中心に本日の注目点のみ。

### 📈 銘柄別分析
★要分析の銘柄のみ詳しく分析：
- 変動幅（上記テーブルの数値をそのまま記載）
- 変動の原因（ニュースから特定できた場合のみ。できない場合は「原因不明」）

軽微な変動の銘柄は特記すべきニュースがある場合のみ1行で言及。

### 🔍 今後の注目ポイント
ニュースから読み取れる範囲のみ、2〜3点。"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return response.choices[0].message.content


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
