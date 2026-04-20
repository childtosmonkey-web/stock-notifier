"""GitHubへのチャート画像アップロード"""

import os
import base64
import requests


def upload_to_github(image_path: str) -> str:
    """画像をGitHubリポジトリにアップロードしてraw URLを返す。"""
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
