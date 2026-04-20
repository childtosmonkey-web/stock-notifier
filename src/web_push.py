"""Web Push通知の送信"""

import os
import json
from pywebpush import webpush, WebPushException


def send_web_push(subscription: dict, payload: dict) -> None:
    """Web Push通知を送信する。"""
    vapid_private_key_b64 = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_claims_email = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:example@example.com")

    if not vapid_private_key_b64:
        raise ValueError("VAPID_PRIVATE_KEY が設定されていません")

    webpush(
        subscription_info=subscription,
        data=json.dumps(payload),
        vapid_private_key=vapid_private_key_b64,
        vapid_claims={"sub": vapid_claims_email},
    )


def send_combined_push(subscription: dict, stocks: list[dict]) -> None:
    """全銘柄をまとめて1通知で送信する。"""
    lines = []
    for s in stocks:
        if s.get("price") is None:
            continue
        direction = "▲" if s["change_pct"] >= 0 else "▼"
        lines.append(f"{s['ticker']} {direction}{abs(s['change_pct']):.2f}%  ${s['price']:.2f}")

    payload = {
        "title": "📈 本日の株価",
        "body": "\n".join(lines),
    }
    send_web_push(subscription, payload)
