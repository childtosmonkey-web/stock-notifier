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
