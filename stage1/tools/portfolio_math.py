"""Validated Stage 1 estimators: unrestricted tangency, long-only and performance.

Preserves the approved computations in a reusable module.
Returns and factors are monthly decimal simple returns; sample covariance ddof=1.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.optimize import minimize


def estimate(returns: pd.DataFrame, rf: pd.Series, covariance_basis: str = "raw_returns") -> dict:
    if covariance_basis not in {"raw_returns", "excess_returns"}:
        raise ValueError("Unknown covariance convention")
    rf = rf.loc[returns.index]
    mean = returns.mean().to_numpy()
    excess = returns.sub(rf, axis=0)
    excess_mean = excess.mean().to_numpy()
    covariance = (returns if covariance_basis == "raw_returns" else excess).cov().to_numpy()
    eigenvalues = np.linalg.eigvalsh(covariance)
    assert np.allclose(covariance, covariance.T, rtol=0, atol=1e-15)
    assert eigenvalues[0] > 0 and np.linalg.matrix_rank(covariance) == len(mean)
    direction = np.linalg.solve(covariance, excess_mean)
    normalization = float(direction.sum())
    direction_norm = float(np.abs(direction).sum())
    if direction_norm == 0:
        raise ValueError("Zero excess means do not identify a unique tangency direction")
    normalized_direction_ratio = normalization / direction_norm
    if normalized_direction_ratio <= 1e-10:
        raise ValueError("No valid positive-Sharpe budget-one tangency: direction normalization is negative or near zero")
    weights = direction / normalization
    residual = float(np.linalg.norm(covariance @ direction - excess_mean, ord=np.inf))
    assert residual < 1e-12 and abs(weights.sum() - 1) < 1e-12
    model_sharpe = float(excess_mean @ weights / np.sqrt(weights @ covariance @ weights) * np.sqrt(12))
    cauchy_bound = float(np.sqrt(excess_mean @ direction * 12))
    assert abs(model_sharpe - cauchy_bound) < 1e-10
    return {"tickers": returns.columns.tolist(), "start_month": returns.index[0], "end_month": returns.index[-1],
        "observations": len(returns), "mean_monthly": mean.tolist(), "mean_rf_monthly": float(rf.mean()),
        "excess_mean_monthly": excess_mean.tolist(), "covariance_monthly": covariance.tolist(),
        "covariance_basis": covariance_basis, "tangency_direction": direction.tolist(),
        "normalization_denominator": normalization, "normalization_direction_ratio": normalized_direction_ratio,
        "weights": weights.tolist(), "covariance_rank": len(mean), "smallest_eigenvalue": float(eigenvalues[0]),
        "largest_eigenvalue": float(eigenvalues[-1]), "condition_number": float(np.linalg.cond(covariance)),
        "linear_solve_max_abs_residual": residual, "model_sharpe_annual": model_sharpe,
        "cauchy_schwarz_bound_annual": cauchy_bound, "positive_tangency_direction_verified": True,
        "gross_exposure": float(abs(weights).sum()), "long_exposure": float(weights[weights > 0].sum()),
        "short_exposure": float(-weights[weights < 0].sum()), "short_position_count": int((weights < 0).sum())}


def long_only_tangency(model: dict) -> dict:
    mean = np.asarray(model["excess_mean_monthly"])
    covariance = np.asarray(model["covariance_monthly"])
    assert mean.max() > 0
    target = mean / mean.max()
    scaled = covariance / np.median(np.diag(covariance))
    best = int(np.argmax(mean / np.sqrt(np.diag(covariance))))
    initial = np.zeros(len(mean)); initial[best] = 1 / target[best]
    solution = minimize(lambda y: float(y @ scaled @ y), initial,
        jac=lambda y: 2 * scaled @ y, method="SLSQP", bounds=[(0, None)] * len(mean),
        constraints=[{"type": "eq", "fun": lambda y: float(target @ y - 1), "jac": lambda y: target}],
        options={"ftol": 1e-13, "maxiter": 3000})
    if not solution.success:
        raise ValueError("Long-only convex quadratic solve failed: " + solution.message)
    y = solution.x
    assert y.min() >= -1e-12 and abs(target @ y - 1) < 1e-10
    gradient = 2 * scaled @ y
    multiplier = float(gradient @ y / (target @ y))
    reduced_gradient = gradient - multiplier * target
    active = y > 1e-7
    active_residual = float(np.max(np.abs(reduced_gradient[active])))
    inactive_minimum = float(np.min(reduced_gradient[~active])) if (~active).any() else 0.0
    assert active_residual < 1e-5 and inactive_minimum > -1e-5
    weights = y / y.sum()
    assert abs(weights.sum() - 1) < 1e-12 and weights.min() >= -1e-12
    return {"weights": weights.tolist(), "method": "Convex minimum variance at fixed positive excess mean, then budget normalization",
        "optimizer": "scipy SLSQP with analytic gradients", "success": True,
        "active_position_count": int((weights > 1e-7).sum()), "maximum_weight": float(weights.max()),
        "gross_exposure": float(np.abs(weights).sum()), "short_exposure": float(-weights[weights < 0].sum()),
        "equality_residual": float(abs(target @ y - 1)), "kkt_active_max_abs_residual": active_residual,
        "kkt_inactive_min_reduced_gradient": inactive_minimum,
        "model_sharpe_annual": float(mean @ weights / np.sqrt(weights @ covariance @ weights) * np.sqrt(12))}


def portfolio_stats(returns: pd.DataFrame, rf: pd.Series, weights: np.ndarray, portfolio: str, evaluation_window: str) -> dict:
    series = returns.to_numpy() @ weights
    excess = series - rf.loc[returns.index].to_numpy()
    annual_vol = float(series.std(ddof=1) * np.sqrt(12))
    annual_excess_vol = float(excess.std(ddof=1) * np.sqrt(12))
    return {"portfolio": portfolio, "evaluation_window": evaluation_window,
        "start_month": returns.index[0], "end_month": returns.index[-1], "observations": len(returns),
        "annual_mean": float(series.mean() * 12), "annual_excess_mean": float(excess.mean() * 12),
        "annual_volatility": annual_vol, "annual_excess_volatility": annual_excess_vol,
        "sharpe_model_annual": float(excess.mean() * 12 / annual_vol),
        "sharpe_realized_excess_annual": float(excess.mean() * 12 / annual_excess_vol),
        "min_month": float(series.min()), "max_month": float(series.max()),
        "gross_exposure": float(abs(weights).sum()), "short_exposure": float(-weights[weights < 0].sum()),
        "maximum_absolute_weight": float(abs(weights).max())}
