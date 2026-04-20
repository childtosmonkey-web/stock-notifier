"""Web Push通知の送信"""

import os
import json
import base64
from pywebpush import webpush, WebPushException


def send_web_push(subscription: dict, payload: dict) -> None:
    """Web Push通知を送信する。"""
    vapid_private_key_b64 = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_claims_email = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:example@example.com")

    if not vapid_private_key_b64:
        raise ValueError("VAPID_PRIVATE_KEY が設定されていません")

    # .env に保存された base64 エンコード済み PEM を復元する
    vapid_private_key = base64.urlsafe_b64decode(vapid_private_key_b64).decode()

    webpush(
        subscription_info=subscription,
        data=json.dumps(payload),
        vapid_private_key=vapid_private_key,
        vapid_claims={"sub": vapid_claims_email},
    )


def send_stock_push(subscription: dict, stock_data: dict, chart_url: str | None = None) -> None:
    """株価Web Push通知を送信する。"""
    ticker = stock_data["ticker"]
    price = stock_data["price"]
    change_pct = stock_data["change_pct"]
    change = stock_data["change"]

    direction = "▲" if change >= 0 else "▼"

    payload = {
        "title": f"{ticker}  {direction}{abs(change_pct):.2f}%",
        "body": f"現在値: ${price:.2f}　前日比: {change:+.2f}",
        "image": chart_url,
        "ticker": ticker,
    }

    send_web_push(subscription, payload)
