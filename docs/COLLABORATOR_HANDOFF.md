# Collaborator handoff

Stage 1 is ready to supply monthly portfolio returns for the next project
stages. Read the current report, run the offline pipeline once, and check
`validation/reproduction.json` before using the inputs.

## Input dictionary

CSV numeric data are stored at full precision in **decimal units**. Only report
and notebook displays convert to percentages and round to three decimals.

| File | Key / shape | Meaning and units |
|---|---|---|
| `data/processed/returns_us_monthly.csv` | `Month`, 130 × 29 | Selected raw simple stock returns; 0.01 means 1% |
| `data/processed/ff3_monthly.csv` | `Month`, 130 × 4 | `Mkt-RF`, `SMB`, `HML`, `RF`, monthly decimals |
| `data/processed/value_weights.csv` | `ticker`, 29 rows | Fixed 2026-08-31 company size weights and source fields |
| `data/processed/market_caps.csv` | `ticker`, 29 rows | Yahoo native company capitalization, USD |
| `data/processed/prices_us_monthly.csv` | `Month`, 131 × 29 | Wealth index, October 2015 = 100; not USD/share prices |
| `data/processed/vendor_adjusted_prices_us_monthly.csv` | `Month`, 131 × 29 | Native Yahoo monthly adjusted close |
| `data/processed/month_end_observation_dates.csv` | `Month`, 131 × 29 | Actual Yahoo last observation dates |
| `data/processed/yahoo_native_returns_monthly.csv` | `Month`, 130 × 29 | Yahoo returns before instructor priority and event replacement |
| `data/processed/corporate_action_return_corrections.csv` | ticker / event date, seven rows | Event-month before / after audit values |
| `results/stage1/estimated_mean_vectors.csv` | `ticker`, 29 rows | Raw and excess arithmetic monthly means |
| `results/stage1/estimated_covariance_monthly.csv` | ordered 29 × 29 | Raw monthly covariance, decimal-return squared |
| `results/stage1/exhibit_1b_weights.csv` | `ticker`, 29 rows | Full-sample tangency, value, long-only weights |
| `results/stage1/exhibit_1c_subsample_weights.csv` | `ticker`, 29 rows | Full-, first- and second-window tangency weights |
| `results/stage1/portfolio_monthly_returns.csv` | `Month`, 130 rows | Fixed-weight main and half-sample raw portfolio returns; RF comes from the factor table |
| `results/stage1/portfolio_statistics.csv` | portfolio / evaluation window, 15 rows | Five fitted weight vectors evaluated in three windows |
| `results/stage1/universe_sensitivity/weights.csv` | `ticker`, 29 rows | Independent 29 / 23 / 6 fits; outside-subset entries missing |
| `results/stage1/universe_sensitivity/portfolio_monthly_returns.csv` | `Month`, 130 rows | Independent subset raw portfolio returns; subtract aligned RF for excess returns |

The sample window and ordered ticker list come from `config/universe.json`.
Column order must match the weight index whenever using matrix multiplication.

## Load the main inputs safely

```python
from pathlib import Path
import numpy as np
import pandas as pd

root = Path('.')  # repository root
returns = pd.read_csv(root / 'data/processed/returns_us_monthly.csv',
                      index_col='Month', float_precision='round_trip')
factors = pd.read_csv(root / 'data/processed/ff3_monthly.csv',
                      index_col='Month', float_precision='round_trip')
weights = pd.read_csv(root / 'results/stage1/exhibit_1b_weights.csv',
                      index_col='ticker', float_precision='round_trip')

assert returns.index.is_unique and factors.index.is_unique
assert returns.index.equals(factors.index)
assert set(returns.columns) == set(weights.index)
assert returns.shape == (130, 29)

w = weights.loc[returns.columns, 'tangency_weight']
assert np.isclose(w.sum(), 1.0)
portfolio_raw = returns @ w
portfolio_excess = portfolio_raw - factors['RF']
regression_inputs = factors[['Mkt-RF', 'SMB', 'HML']].copy()
regression_inputs.insert(0, 'portfolio_excess', portfolio_excess)
assert not regression_inputs.isna().any().any()
```

This prepares the data; factor regressions and alpha inference belong to the
next stages and have not been estimated here. Use the intercept and inference
method required by the assignment. Preserve a clear distinction between fitting
and evaluation periods when adding subsequent tests.

## Keep these distinctions

1. `Mkt-RF` is already a market excess return. Do not subtract RF again.
   `SMB` and `HML` are factor portfolio returns. For the market raw return,
   add RF to `Mkt-RF`.
2. The portfolio return CSV applies each fitted half-sample weight vector to
   all 130 months. Use `portfolio_statistics.csv` with the matching
   `evaluation_window` for the report's fitted half-sample performance.
   First-half weights evaluated in the second half are a separate experiment.
3. The value-weight portfolio uses the sample-end size vector throughout the
   period. It is not the DJIA (which is price weighted) or a monthly historical
   market-cap index.
4. Subset weights are independently fitted. To compute a subset return, select
   its actual stocks and its own weights. Do not treat missing entries as a
   failed data join or renormalize the corresponding 29-stock weights.
5. The report's model Sharpe uses raw-return volatility; the
   `sharpe_realized_excess_annual` field uses excess-return volatility. Retain
   their names and definitions when comparing results.
6. Follow the included seven spin-off replacements when creating a different
   frequency. Do not add child-stock values a second time to a return already
   rebuilt with the same distribution.

## Weekly robustness and new work

The included daily Yahoo and corporate-action caches support later weekly
preparation. Weekly returns still need a consistent week-end rule, corresponding
action replacements, aligned weekly RF / factor returns and separate acceptance.
No weekly robustness result is claimed by this handoff.

Keep the reviewed Stage 1 snapshot unchanged when experimenting. Use a new
branch, write next-stage outputs to a new directory such as `results/stage2/`,
and record the analysis version, fitting window and evaluation window. A new
universe, a new source vintage or a changed event convention should be a named
new version rather than a silent overwrite of the accepted reference.
