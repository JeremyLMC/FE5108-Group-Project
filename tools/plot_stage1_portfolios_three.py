"""Render Exhibit 1b's three portfolios from the accepted Stage 1 weights.

No portfolio is re-estimated. All 29 tickers, source zeros, and small numerical
residuals are preserved. Run in the project's existing Matplotlib environment.
"""

from pathlib import Path
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "results/stage1"
SOURCE = STAGE / "exhibit_1b_weights.csv"
MODELS = STAGE / "results.json"
VALUE_SOURCE = ROOT / "data/processed/value_weights.csv"
OUTPUT = STAGE / "figures/exhibit_1b_three_portfolios"
RECEIPT = ROOT / "validation/report_portfolio_figure.json"
TICKERS = [
    "MMM", "AXP", "AAPL", "BA", "CAT", "CVX", "CSCO", "KO", "XOM",
    "GE", "GS", "HD", "INTC", "IBM", "JNJ", "JPM", "MCD", "MRK",
    "MSFT", "NKE", "PFE", "PG", "TRV", "RTX", "UNH", "VZ", "V",
    "WMT", "DIS",
]
COLUMNS = ["tangency_weight", "value_weight", "long_only_weight"]
LABELS = ["Unrestricted tangency", "Value weighted", "Long-only tangency"]
COLORS = ["#243F59", "#B8873B", "#3C7F7A"]


def main() -> None:
    source_bytes = {p: p.read_bytes() for p in (SOURCE, MODELS, VALUE_SOURCE)}
    frame = pd.read_csv(SOURCE, float_precision="round_trip")
    models = json.loads(MODELS.read_text(encoding="utf-8"))
    value = pd.read_csv(VALUE_SOURCE, float_precision="round_trip")
    assert frame.ticker.tolist() == TICKERS
    assert value.ticker.tolist() == TICKERS
    assert models["models"]["full_sample"]["tickers"] == TICKERS
    expected = [
        models["models"]["full_sample"]["weights"],
        value.value_weight.to_numpy(),
        models["long_only"]["weights"],
    ]
    checks = {}
    for column, vector in zip(COLUMNS, expected):
        observed = frame[column].to_numpy()
        assert observed.shape == (29,)
        assert np.isfinite(observed).all()
        difference = float(np.max(np.abs(observed - np.asarray(vector))))
        assert difference < 1e-13
        assert np.isclose(observed.sum(), 1.0, rtol=0, atol=1e-12)
        checks[column] = {
            "sum": float(observed.sum()),
            "max_abs_source_difference": difference,
            "exact_zero_count": int((observed == 0).sum()),
            "min": float(observed.min()),
            "max": float(observed.max()),
        }
    active_threshold = 1e-10
    active = frame.long_only_weight > active_threshold
    assert int(active.sum()) == models["long_only"]["active_position_count"] == 9
    assert (frame.long_only_weight >= 0).all()
    max_row = frame.loc[frame.long_only_weight.idxmax()]
    assert max_row.ticker == "MSFT"
    assert np.isclose(max_row.long_only_weight, 0.28609051142156683,
                      rtol=0, atol=1e-6)
    assert f"{max_row.long_only_weight * 100:.3f}" == "28.609"

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(1, 2, figsize=(9.8, 5.4), sharex=True)
    split = (len(frame) + 1) // 2
    artists = []
    for ax, sub in zip(axes, (frame.iloc[:split], frame.iloc[split:])):
        y = np.arange(len(sub))
        for series, column in enumerate(COLUMNS):
            bars = ax.barh(y + (series - 1) * 0.26, sub[column],
                           height=0.245, color=COLORS[series])
            assert np.allclose([bar.get_width() for bar in bars], sub[column],
                               rtol=0, atol=0)
            artists.extend(bars)
        ax.set_yticks(y, sub.ticker)
        ax.invert_yaxis()
        ax.set_xlim((-0.55, 0.55))
        ax.set_xticks([-0.4, -0.2, 0, 0.2, 0.4])
        ax.axvline(0, color="#555555", linewidth=0.7)
        ax.grid(axis="x", color="#dddddd", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_xlabel("Portfolio weight")
    assert len(artists) == 87
    fig.legend([Patch(facecolor=color) for color in COLORS], LABELS,
               loc="upper center", ncol=3, frameon=False,
               columnspacing=1.6, handlelength=1.8)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        path = OUTPUT.with_suffix(f".{ext}")
        fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
        print(path.relative_to(ROOT).as_posix())
    plt.close(fig)
    for path, before in source_bytes.items():
        assert path.read_bytes() == before, "Source data were modified"
    with Image.open(OUTPUT.with_suffix(".png")) as im:
        dimensions = list(im.size)
    receipt = {
        "status": "pass",
        "scope": "Exhibit 1b three-portfolio weight comparison only",
        "source_csv": SOURCE.relative_to(ROOT).as_posix(),
        "source_models": MODELS.relative_to(ROOT).as_posix(),
        "source_value_weights": VALUE_SOURCE.relative_to(ROOT).as_posix(),
        "ticker_order": TICKERS,
        "checks": checks,
        "long_only_positive_positions_at_threshold": int(active.sum()),
        "positive_position_threshold": active_threshold,
        "long_only_numerical_residual_count": int(
            ((frame.long_only_weight > 0) & ~active).sum()),
        "long_only_largest_ticker": str(max_row.ticker),
        "long_only_largest_weight": float(max_row.long_only_weight),
        "bar_count_including_zero_weights": len(artists),
        "axis_limits": [-0.55, 0.55],
        "common_scale": True,
        "source_bytes_preserved": True,
        "outputs": [OUTPUT.with_suffix(ext).relative_to(ROOT).as_posix()
                    for ext in (".png", ".svg")],
        "png_dimensions": dimensions,
        "visual_review": "not performed by this script",
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(RECEIPT.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
