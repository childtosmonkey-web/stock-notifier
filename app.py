"""FastAPI Webアプリ"""

import os
import json
import base64
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True)

app = FastAPI()
app.mount("/web", StaticFiles(directory="web"), name="web")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "childtosmonkey-web")
GITHUB_REPO = "stock-notifier"
CONFIG_PATH = "config.json"
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")

GH_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}
CONFIG_API_URL = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{CONFIG_PATH}"


def _get_remote_config() -> tuple[dict, str]:
    """GitHubからconfig.jsonを取得し (data, sha) を返す。"""
    r = requests.get(CONFIG_API_URL, headers=GH_HEADERS, timeout=10)
    r.raise_for_status()
    body = r.json()
    data = json.loads(base64.b64decode(body["content"]).decode())
    return data, body["sha"]


def _save_remote_config(data: dict, sha: str) -> None:
    """config.jsonをGitHubに保存する。"""
    content = base64.b64encode(json.dumps(data, indent=2, ensure_ascii=False).encode()).decode()
    payload = {"message": "Update config.json", "content": content, "sha": sha}
    r = requests.put(CONFIG_API_URL, headers=GH_HEADERS, json=payload, timeout=30)
    r.raise_for_status()


# ── ルート ──────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse("web/index.html")


@app.get("/sw.js")
def service_worker():
    return FileResponse("web/sw.js", media_type="application/javascript")


_chart_cache: dict = {}
_CHART_TTL = 300

_stocks_cache: dict = {"ts": 0, "data": {}}
_CACHE_TTL = 300  # 5分キャッシュ

@app.get("/api/stocks")
def get_stocks():
    """全監視銘柄の最新株価＋チャートURLを返す。"""
    import time
    config, _ = _get_remote_config()
    tickers = config.get("tickers", [])

    now = time.time()
    cached = _stocks_cache
    if now - cached["ts"] < _CACHE_TTL and set(tickers) == set(cached["data"].keys()):
        return {"stocks": list(cached["data"].values())}

    import datetime as _dt
    results = {}
    for ticker in tickers:
        entry: dict = {"ticker": ticker, "price": None, "change_pct": None, "change": None, "bars": []}
        if POLYGON_API_KEY:
            try:
                # 6ヶ月分の日足を1回で取得（全期間の切り替えをフロント側で処理）
                to_dt = _dt.datetime.utcnow()
                from_dt = to_dt - _dt.timedelta(days=185)
                r = requests.get(
                    f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day"
                    f"/{from_dt.strftime('%Y-%m-%d')}/{to_dt.strftime('%Y-%m-%d')}",
                    params={"adjusted": "true", "sort": "asc", "limit": 200, "apiKey": POLYGON_API_KEY},
                    timeout=8,
                )
                if r.ok:
                    items = r.json().get("results", [])
                    if items:
                        last = items[-1]
                        c, o = last["c"], items[-2]["c"] if len(items) > 1 else last["o"]
                        chg = round(c - o, 2)
                        chg_pct = round((chg / o) * 100, 2)
                        entry.update({"price": c, "change": chg, "change_pct": chg_pct})
                        entry["bars"] = [{"time": i["t"] // 1000, "open": i["o"],
                                          "high": i["h"], "low": i["l"], "close": i["c"]}
                                         for i in items]
            except Exception:
                pass
        results[ticker] = entry

    _stocks_cache["ts"] = now
    _stocks_cache["data"] = results
    return {"stocks": list(results.values())}


@app.get("/api/chart/{ticker}")
def get_chart_data(ticker: str, period: str = "1m"):
    import time as _time, datetime
    cache_key = f"{ticker}:{period}"
    now = _time.time()
    if cache_key in _chart_cache and now - _chart_cache[cache_key]["ts"] < _CHART_TTL:
        return _chart_cache[cache_key]["data"]

    period_cfg = {
        "1h": {"multiplier": 1,  "timespan": "minute", "days": 1},
        "1d": {"multiplier": 5,  "timespan": "minute", "days": 2},
        "1w": {"multiplier": 1,  "timespan": "hour",   "days": 7},
        "1m": {"multiplier": 1,  "timespan": "day",    "days": 30},
        "3m": {"multiplier": 1,  "timespan": "day",    "days": 90},
        "6m": {"multiplier": 1,  "timespan": "day",    "days": 180},
        "1y": {"multiplier": 1,  "timespan": "day",    "days": 365},
    }
    cfg = period_cfg.get(period, period_cfg["1m"])
    to_dt = datetime.datetime.utcnow()
    from_dt = to_dt - datetime.timedelta(days=cfg["days"])

    bars = []
    if POLYGON_API_KEY:
        try:
            r = requests.get(
                f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range"
                f"/{cfg['multiplier']}/{cfg['timespan']}"
                f"/{from_dt.strftime('%Y-%m-%d')}/{to_dt.strftime('%Y-%m-%d')}",
                params={"adjusted": "true", "sort": "asc", "limit": 500, "apiKey": POLYGON_API_KEY},
                timeout=10,
            )
            if r.ok:
                for item in r.json().get("results", []):
                    bars.append({
                        "time": item["t"] // 1000,
                        "open": item["o"], "high": item["h"],
                        "low": item["l"],  "close": item["c"],
                    })
        except Exception:
            pass

    data = {"bars": bars}
    _chart_cache[cache_key] = {"ts": now, "data": data}
    return data


@app.get("/api/search")
def search_tickers(q: str = ""):
    """ティッカー・英語社名で検索して候補を返す。"""
    q = q.strip()
    if not q:
        return {"results": []}

    results: list[dict] = []
    if POLYGON_API_KEY:
        try:
            r = requests.get(
                "https://api.polygon.io/v3/reference/tickers",
                params={"search": q, "active": "true", "market": "stocks", "limit": 15, "apiKey": POLYGON_API_KEY},
                timeout=5,
            )
            if r.ok:
                items = r.json().get("results", [])
                q_upper = q.upper()
                # ティッカー完全一致を先頭に並べる
                exact = [i for i in items if i.get("ticker", "").upper() == q_upper]
                others = [i for i in items if i.get("ticker", "").upper() != q_upper]
                for item in exact + others:
                    results.append({"ticker": item.get("ticker", ""), "name": item.get("name", "")})
        except Exception:
            pass

    return {"results": results[:15]}


@app.get("/api/vapid-public-key")
def get_vapid_public_key():
    return {"key": VAPID_PUBLIC_KEY}


@app.get("/api/config")
def get_config():
    config, _ = _get_remote_config()
    return config


class TickerUpdate(BaseModel):
    tickers: list[str]


@app.put("/api/config/tickers")
def update_tickers(body: TickerUpdate):
    tickers = [t.upper().strip() for t in body.tickers if t.strip()]
    if not tickers:
        raise HTTPException(status_code=400, detail="銘柄リストが空です")
    config, sha = _get_remote_config()
    config["tickers"] = tickers
    _save_remote_config(config, sha)
    return {"tickers": tickers}


class NotifyHourUpdate(BaseModel):
    notify_hour: int


@app.put("/api/config/notify-hour")
def update_notify_hour(body: NotifyHourUpdate):
    if not 0 <= body.notify_hour <= 23:
        raise HTTPException(status_code=400, detail="時刻は0〜23で指定してください")
    config, sha = _get_remote_config()
    config["notify_hour"] = body.notify_hour
    _save_remote_config(config, sha)
    return {"notify_hour": body.notify_hour}


class SubscribeBody(BaseModel):
    subscription: dict


@app.post("/api/subscribe")
def subscribe(body: SubscribeBody):
    config, sha = _get_remote_config()
    config["push_subscription"] = body.subscription
    _save_remote_config(config, sha)
    return {"status": "ok"}


@app.post("/api/notify")
def trigger_notify():
    """GitHub Actions を手動トリガーする。"""
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/actions/workflows/notify.yml/dispatches"
    r = requests.post(url, headers=GH_HEADERS, json={"ref": "main"}, timeout=10)
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail=f"GitHub Actions trigger failed: {r.text}")
    return {"status": "triggered"}
