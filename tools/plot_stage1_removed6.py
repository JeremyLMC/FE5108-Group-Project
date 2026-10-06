"""Plot the independent tangency portfolio of six later DJIA removals.

The input is the reviewed, separately estimated six-stock weight vector.
This script only renders existing results and does not fetch or re-fit data.
Install the repository requirements before running.
"""

from pathlib import Path
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/stage1/universe_sensitivity"
TICKERS = ["XOM", "GE", "INTC", "PFE", "RTX", "VZ"]
BLUE = "#243F59"


def main() -> None:
    all_weights = pd.read_csv(OUT / "weights.csv")
    result = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    model = result["models"]["later_removals_6"]
    frame = all_weights.loc[all_weights.weight_6.notna()].copy()
    assert frame.ticker.tolist() == TICKERS == model["tickers"]
    assert np.isclose(frame.weight_6.sum(), 1.0)
    assert np.isclose(frame.weight_6.abs().sum(), model["gross_exposure"])
    assert (frame.weight_6 < 0).sum() == 1
    assert frame.loc[frame.weight_6 < 0, "ticker"].item() == "PFE"

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.fonttype": "none",
    })
    fig, ax = plt.subplots(figsize=(9.8, 2.7))
    y = np.arange(len(frame))
    bars = ax.barh(y, frame.weight_6, height=0.60, color=BLUE)
    ax.set_yticks(y, frame.ticker)
    ax.invert_yaxis()
    ax.set_xlim(-0.09, 0.64)
    ax.set_xticks([-0.05, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.axvline(0, color="#555555", linewidth=0.7)
    ax.grid(axis="x", color="#dddddd", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_xlabel("Portfolio weight")

    for bar, value in zip(bars, frame.weight_6):
        ax.annotate(f"{value * 100:.3f}%",
                    xy=(value, bar.get_y() + bar.get_height() / 2),
                    xytext=(5 if value >= 0 else -5, 0),
                    textcoords="offset points",
                    ha="left" if value >= 0 else "right",
                    va="center", color="#222222", fontsize=9)
    fig.tight_layout(pad=0.8)
    directory = OUT / "figures"
    directory.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        target = directory / f"removed6_weights.{ext}"
        fig.savefig(target, dpi=220, bbox_inches="tight", facecolor="white")
        print(target)
    plt.close(fig)


if __name__ == "__main__":
    main()
