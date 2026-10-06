"""Render three-series Stage 1 weight comparisons from reviewed results.

No analysis is re-estimated.  Subset portfolios are embedded into the original
29-stock universe for display: source NaNs become structural zero weights
(not held) only in the plotting copy.  The source data and earlier figures
are preserved.  Run with the project's existing Matplotlib environment.
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


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "results/stage1"
SUBSET = STAGE / "universe_sensitivity"
TICKERS = [
    "MMM", "AXP", "AAPL", "BA", "CAT", "CVX", "CSCO", "KO", "XOM",
    "GE", "GS", "HD", "INTC", "IBM", "JNJ", "JPM", "MCD", "MRK",
    "MSFT", "NKE", "PFE", "PG", "TRV", "RTX", "UNH", "VZ", "V",
    "WMT", "DIS",
]
COLORS = ["#243F59", "#B8873B", "#3C7F7A"]


def check_model(frame: pd.DataFrame, column: str, model: dict) -> None:
    """Verify observed holdings against their independent fitted model."""
    present = frame.loc[frame[column].notna(), ["ticker", column]]
    assert present.ticker.tolist() == model["tickers"]
    observed = present[column].to_numpy()
    assert np.allclose(observed, model["weights"], rtol=0, atol=1e-13)
    assert np.isclose(observed.sum(), 1.0, rtol=0, atol=1e-12)
    assert np.isfinite(observed).all()


def paired_three(frame: pd.DataFrame, columns: list, labels: list,
                 output: Path, limits: tuple, ticks: list,
                 footnote: str = "") -> None:
    assert frame.ticker.tolist() == TICKERS
    assert len(columns) == len(labels) == 3
    assert frame[columns].notna().all().all()
    assert np.allclose(frame[columns].sum().to_numpy(), 1.0,
                       rtol=0, atol=1e-12)
    fig, axes = plt.subplots(1, 2, figsize=(9.8, 5.65 if footnote else 5.4),
                             sharex=True)
    split = (len(frame) + 1) // 2
    for ax, sub in zip(axes, (frame.iloc[:split], frame.iloc[split:])):
        y = np.arange(len(sub))
        for series, column in enumerate(columns):
            ax.barh(y + (series - 1) * 0.26, sub[column],
                    height=0.245, color=COLORS[series])
        ax.set_yticks(y, sub.ticker)
        ax.invert_yaxis()
        ax.set_xlim(limits)
        ax.set_xticks(ticks)
        ax.axvline(0, color="#555555", linewidth=0.7)
        ax.grid(axis="x", color="#dddddd", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_xlabel("Portfolio weight")
    handles = [Patch(facecolor=color) for color in COLORS]
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False,
               columnspacing=1.6, handlelength=1.8)
    bottom = 0.047 if footnote else 0.0
    if footnote:
        fig.text(0.5, 0.013, footnote, ha="center", va="bottom",
                 fontsize=8.0, color="#555555")
    fig.tight_layout(rect=(0, bottom, 1, 0.93))
    output.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        path = output.with_suffix(f".{ext}")
        fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
        print(path)
    plt.close(fig)


def main() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.fonttype": "none",
    })
    time_source = STAGE / "exhibit_1c_subsample_weights.csv"
    subset_source = SUBSET / "weights.csv"
    source_bytes = {path: path.read_bytes()
                    for path in (time_source, subset_source)}
    time_frame = pd.read_csv(time_source)
    time_models = json.loads((STAGE / "results.json").read_text(
        encoding="utf-8"))["models"]
    time_columns = ["full_sample_weight", "first_half_weight",
                    "second_half_weight"]
    for column, model_name in zip(time_columns,
                                  ("full_sample", "first_half", "second_half")):
        check_model(time_frame, column, time_models[model_name])
    paired_three(time_frame, time_columns,
                 ["Full-sample tangency", "First-half tangency",
                  "Second-half tangency"],
                 STAGE / "figures/time_weights_three", (-0.92, 0.90),
                 [-0.75, -0.50, -0.25, 0, 0.25, 0.50, 0.75])

    subset_frame = pd.read_csv(subset_source)
    subset_models = json.loads((SUBSET / "results.json").read_text(
        encoding="utf-8"))["models"]
    subset_columns = ["weight_29", "weight_23", "weight_6"]
    for column, model_name in zip(subset_columns,
                                  ("all_29", "retained_23", "later_removals_6")):
        check_model(subset_frame, column, subset_models[model_name])
    assert subset_frame.weight_23.isna().sum() == 6
    assert subset_frame.weight_6.isna().sum() == 23
    assert (subset_frame.weight_23.notna() ^
            subset_frame.weight_6.notna()).all()
    subset_plot = subset_frame.copy()
    for column in subset_columns:
        observed = subset_frame[column].notna()
        subset_plot[column] = subset_frame[column].fillna(0.0)
        assert np.array_equal(subset_plot.loc[observed, column].to_numpy(),
                              subset_frame.loc[observed, column].to_numpy())
        assert (subset_plot.loc[~observed, column] == 0).all()
    paired_three(subset_plot, subset_columns,
                 ["All 29 tangency", "Retained 23 tangency",
                  "Later-removal 6 tangency"],
                 SUBSET / "figures/weights_three", (-0.56, 0.64),
                 [-0.4, -0.2, 0, 0.2, 0.4, 0.6],
                 "Stocks outside a subset have structural zero weights "
                 "(not held), rather than estimated weights.")
    for path, before in source_bytes.items():
        assert path.read_bytes() == before, "Source CSV was modified"
    print("Verified six model vectors; sums equal one. "
          "Source NaNs preserved; plot-only structural zeros applied.")


if __name__ == "__main__":
    main()
