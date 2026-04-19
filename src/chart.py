"""チャート画像の生成（mplfinance）"""

import os
import matplotlib
if os.environ.get("MPLBACKEND") == "Agg" or not os.environ.get("DISPLAY"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import mplfinance as mpf

# MacのヒラギノフォントでUnicode文字を正しく表示する
from matplotlib import font_manager
_hiragino = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
if os.path.exists(_hiragino):
    font_manager.fontManager.addfont(_hiragino)
    matplotlib.rcParams["font.family"] = "Hiragino Sans"


def generate_chart(ticker: str, ohlcv_data: list[dict], output_dir: str = "/tmp") -> str:
    """30日間のローソク足チャートを生成して画像パスを返す。"""
    df = pd.DataFrame(ohlcv_data)
    df["Date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("Date")
    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })

    output_path = os.path.join(output_dir, f"chart_{ticker}.jpg")

    mc = mpf.make_marketcolors(
        up="#ef5350",
        down="#26a69a",
        edge="inherit",
        wick="inherit",
        volume="in",
    )
    style = mpf.make_mpf_style(
        marketcolors=mc,
        base_mpf_style="nightclouds",
        gridstyle=":",
        y_on_right=False,
    )

    mpf.plot(
        df,
        type="candle",
        style=style,
        title=f"\n{ticker} - 30-Day Chart",
        ylabel="Price (USD)",
        volume=True,
        savefig=dict(fname=output_path, dpi=150, bbox_inches="tight", format="jpg"),
    )

    return output_path
