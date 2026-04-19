"""LINE Messaging API への通知送信"""

import os
import requests


LINE_API_URL = "https://api.line.me/v2/bot/message/push"


def _headers() -> dict:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise ValueError("LINE_CHANNEL_ACCESS_TOKEN が設定されていません")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def send_text(user_id: str, text: str) -> None:
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }
    resp = requests.post(LINE_API_URL, headers=_headers(), json=payload, timeout=10)
    resp.raise_for_status()


def _upload_to_github(image_path: str) -> str:
    """画像をGitHubリポジトリにアップロードしてraw URLを返す。"""
    import base64
    token = os.environ.get("GITHUB_TOKEN")
    username = os.environ.get("GITHUB_USERNAME", "childtosmonkey-web")
    repo = "stock-notifier"
    filename = os.path.basename(image_path)
    api_url = f"https://api.github.com/repos/{username}/{repo}/contents/charts/{filename}"
    headers = {"Authorization": f"token {token}"}

    with open(image_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    existing = requests.get(api_url, headers=headers, timeout=10)
    payload = {"message": f"Update {filename}", "content": content}
    if existing.status_code == 200:
        payload["sha"] = existing.json()["sha"]

    resp = requests.put(api_url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return f"https://raw.githubusercontent.com/{username}/{repo}/main/charts/{filename}"


def send_image(user_id: str, image_path: str) -> None:
    """画像をGitHub経由でLINEに送信する。"""
    image_url = _upload_to_github(image_path)

    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url,
            }
        ],
    }
    resp = requests.post(LINE_API_URL, headers=_headers(), json=payload, timeout=10)
    resp.raise_for_status()


def send_stock_notification(stock_data: dict, chart_path: str | None = None) -> None:
    """株価テキスト＋チャート画像をLINEに送信する。"""
    user_id = os.environ.get("LINE_USER_ID")
    if not user_id:
        raise ValueError("LINE_USER_ID が設定されていません")

    from config import MESSAGE_TEMPLATE
    text = MESSAGE_TEMPLATE.format(
        ticker=stock_data["ticker"],
        price=stock_data["price"],
        change=stock_data["change"],
        change_pct=stock_data["change_pct"],
    )
    send_text(user_id, text)

    if chart_path and os.path.exists(chart_path):
        send_image(user_id, chart_path)
