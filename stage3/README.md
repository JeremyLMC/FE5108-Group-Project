# Stage 3 Factors

Track A, Stage 3 of the FE5108 midterm group project. This package keeps the
Stage 2 sample fixed and compares the one-factor CAPM with the Fama-French
three-factor model. The added factors are SMB (size) and HML (value), the two
additional factors requested by the handout and covered by the Weeks 5-6
course material.

## Reproduce

From the repository root:

```bash
python -m pip install -r stage3/requirements.txt
python stage3/run_stage3.py
python stage3/build_report.py
```

Both commands work offline. The analysis reads only the frozen CSVs in
`stage3/data/`; it does not download or silently refresh historical data.

## Controlled design

| Item | Definition |
|---|---|
| Universe | Same 29 historical DJIA stocks as Stages 1-2 |
| Window | November 2015-August 2026, 130 common monthly observations |
| Dependent variable | Stock raw simple return minus contemporaneous RF |
| CAPM baseline | `Mkt-RF` |
| FF3 model | `Mkt-RF`, `SMB`, `HML` |
| Main inference | Conventional OLS, matching Stage 2 |
| Joint robustness | Gibbons-Ross-Shanken test for CAPM and FF3 |

`RF` is subtracted once from stock returns. `Mkt-RF`, `SMB` and `HML` are
already decimal factor returns and are not divided by 100 or adjusted again.
Keeping dates and observations identical makes the alpha comparison a change
in model specification, not a change in sample.

## Required exhibits

| Requirement | Implementation |
|---|---|
| 3a factor construction | Report paragraphs describing Kenneth French SMB and HML construction and interpretation |
| 3b alphas before versus after | `figures/alpha_before_after.png`, `results/alpha_comparison.csv` |
| 3c anomaly verdict | `results/stage2_anomaly_verdicts.csv` and report discussion of MSFT, WMT and DIS |

The verdict labels are transparent descriptive rules. A Stage 2 significant
alpha is `Absorbed` when its absolute FF3 alpha falls by at least half and its
FF3 `|t(alpha)|` no longer exceeds 2; it is `Partially absorbed` when it loses
significance but falls by less than half, and `Survives` when it remains above
the threshold. Economic magnitude and exact estimates remain visible so the
label does not replace judgment.

## Package map

| Path | Purpose |
|---|---|
| `data/` | Frozen copies of the Stage 2 stock returns and FF3 factors |
| `run_stage3.py` | One-command analytical reproduction and validation |
| `stage3_analysis.ipynb` | Executable walkthrough of exhibits 3b-3c and the joint test |
| `build_report.py` | Four-page report generator |
| `results/` | FF3 coefficients, alpha comparison, focused verdicts and joint tests |
| `figures/` | Main before-versus-after alpha exhibit |
| `reports/` | Reviewed Stage 3 PDF |
| `validation/` | Numerical and report QA receipts |

The GRS test is a robustness check beyond the minimum Stage 3 exhibits. Its
validity depends on the usual multivariate regression assumptions, including
independent and normally distributed disturbances. It should be read together
with the stock-level estimates rather than as a substitute for them.
