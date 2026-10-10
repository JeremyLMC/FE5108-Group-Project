"""Reproduce Track A Stage 3 from frozen Stage 1/2 inputs.

The controlled comparison keeps the Stage 2 sample fixed and changes only the
right-hand side: CAPM (Mkt-RF) versus Fama-French 3 factors (Mkt-RF, SMB, HML).
"""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

BASE = Path(__file__).resolve().parent
STAGE2 = BASE.parent / "stage2"
FACTOR_COLS = ["Mkt-RF", "SMB", "HML"]
STAGE2_SIGNALS = ["MSFT", "WMT", "DIS"]


def fit_models(excess: pd.DataFrame, factors: pd.DataFrame, columns: list[str], prefix: str):
    """Fit one time-series OLS model per stock and return estimates and residuals."""
    X = sm.add_constant(factors[columns])
    rows, residuals = [], {}
    for ticker in excess:
        model = sm.OLS(excess[ticker], X).fit()
        row = {
            "Ticker": ticker,
            f"{prefix}_Alpha_monthly": model.params["const"],
            f"{prefix}_t_Alpha": model.tvalues["const"],
            f"{prefix}_p_Alpha": model.pvalues["const"],
            f"{prefix}_R_squared": model.rsquared,
            f"{prefix}_Adj_R_squared": model.rsquared_adj,
            f"{prefix}_Residual_std_monthly": np.sqrt(model.mse_resid),
            f"{prefix}_N": int(model.nobs),
        }
        for factor in columns:
            safe = factor.replace("-", "_")
            row[f"{prefix}_Beta_{safe}"] = model.params[factor]
            row[f"{prefix}_t_{safe}"] = model.tvalues[factor]
        rows.append(row)
        residuals[ticker] = model.resid
        identity = model.params["const"] + sum(
            model.params[factor] * factors[factor].mean() for factor in columns
        )
        assert abs(excess[ticker].mean() - identity) < 1e-12
    return pd.DataFrame(rows), pd.DataFrame(residuals, index=excess.index)


def grs_test(alphas: np.ndarray, residuals: pd.DataFrame, factors: pd.DataFrame):
    """Gibbons-Ross-Shanken finite-sample F test."""
    T, N = residuals.shape
    K = factors.shape[1]
    assert T > N + K
    e = residuals.to_numpy()
    demeaned_f = factors.to_numpy() - factors.mean().to_numpy()
    # GRS notation: residual covariance uses regression residual degrees of
    # freedom, while the factor second-moment matrix uses divisor T.
    sigma_e = e.T @ e / (T - K - 1)
    omega_f = demeaned_f.T @ demeaned_f / T
    mean_f = factors.mean().to_numpy()
    scale = (T / N) * ((T - N - K) / (T - K - 1))
    denominator = 1.0 + mean_f @ np.linalg.solve(omega_f, mean_f)
    statistic = scale * (alphas @ np.linalg.solve(sigma_e, alphas)) / denominator
    p_value = stats.f.sf(statistic, N, T - N - K)
    return {
        "GRS_statistic": float(statistic),
        "p_value": float(p_value),
        "df1": int(N),
        "df2": int(T - N - K),
        "factor_count": int(K),
    }


def main():
    for name in ("data", "results", "figures", "validation", "reports"):
        (BASE / name).mkdir(exist_ok=True)

    returns = pd.read_csv(BASE / "data/returns_us_monthly.csv", index_col="Month", float_precision="round_trip")
    factors = pd.read_csv(BASE / "data/ff3_monthly.csv", index_col="Month", float_precision="round_trip")
    expected = pd.period_range("2015-11", "2026-08", freq="M").astype(str).tolist()
    assert returns.index.is_unique and factors.index.is_unique
    assert returns.index.tolist() == factors.index.tolist() == expected
    assert returns.shape == (130, 29)
    assert list(factors.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert np.isfinite(returns.to_numpy()).all() and np.isfinite(factors.to_numpy()).all()

    # RF is subtracted once from raw stock returns. All factors are already decimals.
    excess = returns.sub(factors["RF"], axis=0)
    capm, capm_residuals = fit_models(excess, factors, ["Mkt-RF"], "CAPM")
    ff3, ff3_residuals = fit_models(excess, factors, FACTOR_COLS, "FF3")
    comparison = capm.merge(ff3, on="Ticker", validate="one_to_one")
    comparison["Alpha_change_monthly"] = comparison["FF3_Alpha_monthly"] - comparison["CAPM_Alpha_monthly"]
    comparison["Abs_alpha_reduction_monthly"] = (
        comparison["CAPM_Alpha_monthly"].abs() - comparison["FF3_Alpha_monthly"].abs()
    )
    comparison["Abs_alpha_reduction_fraction"] = np.where(
        comparison["CAPM_Alpha_monthly"].abs() > 0,
        comparison["Abs_alpha_reduction_monthly"] / comparison["CAPM_Alpha_monthly"].abs(),
        np.nan,
    )
    comparison["CAPM_abs_t_gt_2"] = comparison["CAPM_t_Alpha"].abs() > 2
    comparison["FF3_abs_t_gt_2"] = comparison["FF3_t_Alpha"].abs() > 2
    comparison["Delta_R_squared"] = comparison["FF3_R_squared"] - comparison["CAPM_R_squared"]

    # A transparent verdict based on economic magnitude and the handout's |t| > 2 rule.
    def verdict(row):
        before, after = abs(row.CAPM_Alpha_monthly), abs(row.FF3_Alpha_monthly)
        if row.CAPM_abs_t_gt_2 and not row.FF3_abs_t_gt_2:
            return "Absorbed" if after <= 0.5 * before else "Partially absorbed"
        if row.CAPM_abs_t_gt_2 and row.FF3_abs_t_gt_2:
            return "Survives"
        if after <= 0.5 * before:
            return "Shrinks materially"
        if after > before:
            return "Not absorbed"
        return "Changes modestly"
    comparison["Verdict"] = comparison.apply(verdict, axis=1)

    comparison.to_csv(BASE / "results/alpha_comparison.csv", index=False)
    ff3.to_csv(BASE / "results/ff3_results.csv", index=False)
    focused = comparison.loc[comparison.Ticker.isin(STAGE2_SIGNALS)].copy()
    focused["Stage2_order"] = focused.Ticker.map({x: i for i, x in enumerate(STAGE2_SIGNALS)})
    focused.sort_values("Stage2_order").drop(columns="Stage2_order").to_csv(
        BASE / "results/stage2_anomaly_verdicts.csv", index=False
    )

    factor_summary = pd.DataFrame({
        "Factor": FACTOR_COLS,
        "Mean_monthly": [factors[c].mean() for c in FACTOR_COLS],
        "Std_monthly": [factors[c].std(ddof=1) for c in FACTOR_COLS],
        "Annualized_arithmetic_mean": [12 * factors[c].mean() for c in FACTOR_COLS],
        "Annualized_volatility": [np.sqrt(12) * factors[c].std(ddof=1) for c in FACTOR_COLS],
    })
    factor_summary.to_csv(BASE / "results/factor_summary.csv", index=False)

    joint = pd.DataFrame([
        {"Model": "CAPM", **grs_test(capm.CAPM_Alpha_monthly.to_numpy(), capm_residuals, factors[["Mkt-RF"]])},
        {"Model": "Fama-French 3-factor", **grs_test(ff3.FF3_Alpha_monthly.to_numpy(), ff3_residuals, factors[FACTOR_COLS])},
    ])
    joint.to_csv(BASE / "results/joint_alpha_tests.csv", index=False)

    # Exhibit 3b: direct paired comparison of monthly alpha estimates.
    plot = comparison.sort_values("CAPM_Alpha_monthly").reset_index(drop=True)
    ypos = np.arange(len(plot))
    fig, ax = plt.subplots(figsize=(8.8, 8.0))
    ax.hlines(ypos, plot.CAPM_Alpha_monthly, plot.FF3_Alpha_monthly, color="#B7C3CC", lw=1.6)
    ax.scatter(plot.CAPM_Alpha_monthly, ypos, color="#245A81", s=30, label="CAPM alpha", zorder=3)
    ax.scatter(plot.FF3_Alpha_monthly, ypos, color="#D17A22", s=30, label="FF3 alpha", zorder=3)
    for i, row in plot.iterrows():
        if row.Ticker in STAGE2_SIGNALS:
            ax.get_yticklabels()
            ax.scatter(row.FF3_Alpha_monthly, i, facecolors="none", edgecolors="#8B1E3F", s=82, lw=1.5, zorder=4)
    ax.axvline(0, color="#555555", lw=0.8)
    ax.set_yticks(ypos, plot.Ticker, fontsize=8)
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set_xlabel("Estimated monthly alpha")
    ax.grid(axis="x", alpha=0.18)
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(BASE / "figures/alpha_before_after.png", dpi=300)
    plt.close(fig)

    summary = {
        "sample_start": expected[0], "sample_end": expected[-1], "T": 130, "N": 29,
        "added_factors": ["SMB", "HML"],
        "capm_significant_alpha_count": int(comparison.CAPM_abs_t_gt_2.sum()),
        "ff3_significant_alpha_count": int(comparison.FF3_abs_t_gt_2.sum()),
        "capm_significant_tickers": comparison.loc[comparison.CAPM_abs_t_gt_2, "Ticker"].tolist(),
        "ff3_significant_tickers": comparison.loc[comparison.FF3_abs_t_gt_2, "Ticker"].tolist(),
        "median_abs_alpha_capm": float(comparison.CAPM_Alpha_monthly.abs().median()),
        "median_abs_alpha_ff3": float(comparison.FF3_Alpha_monthly.abs().median()),
        "mean_R_squared_capm": float(comparison.CAPM_R_squared.mean()),
        "mean_R_squared_ff3": float(comparison.FF3_R_squared.mean()),
        "stage2_signal_verdicts": dict(zip(focused.Ticker, focused.Verdict)),
        "inference": "Conventional OLS for direct Stage 2 comparability; GRS reported as a joint robustness test",
    }
    (BASE / "results/stage3_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    # Ensure the controlled CAPM rerun exactly matches the Stage 2 accepted outputs.
    accepted = pd.read_csv(STAGE2 / "results/capm_results.csv")
    checks = {
        "Alpha": float(np.max(np.abs(accepted.Alpha_monthly - capm.CAPM_Alpha_monthly))),
        "Beta": float(np.max(np.abs(accepted.Beta - capm.CAPM_Beta_Mkt_RF))),
        "t_Alpha": float(np.max(np.abs(accepted.t_Alpha - capm.CAPM_t_Alpha))),
        "R_squared": float(np.max(np.abs(accepted.R_squared - capm.CAPM_R_squared))),
    }
    assert max(checks.values()) < 1e-12
    validation = {
        "status": "passed",
        "checks": [
            "130 contiguous common months; 29 assets; finite inputs",
            "CAPM rerun matches the Stage 2 accepted coefficients",
            "OLS mean identity holds for every stock under both models",
            "FF3 nests CAPM and does not reduce in-sample R squared",
            "GRS dimensions and degrees of freedom are valid",
        ],
        "stage2_max_absolute_differences": checks,
        "minimum_delta_R_squared": float(comparison.Delta_R_squared.min()),
        "inputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE / "data").glob("*.csv")},
        "python": platform.python_version(),
        "packages": {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "scipy", "statsmodels", "matplotlib"]},
    }
    assert validation["minimum_delta_R_squared"] > -1e-12
    (BASE / "validation/reproduction.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(comparison[["Ticker", "CAPM_Alpha_monthly", "CAPM_t_Alpha", "FF3_Alpha_monthly", "FF3_t_Alpha", "Verdict"]].to_string(index=False))
    print("\nJoint tests\n", joint.to_string(index=False))
    print("\n", json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
