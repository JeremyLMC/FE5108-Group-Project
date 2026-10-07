# FE5108 Group Project

Reproducible Stage 1 handoff for **Portfolio choice**. The reviewed report is
[Stage1_Portfolio_Choice_1007.pdf](reports/stage1/Stage1_Portfolio_Choice_1007.pdf).
The editable version is
[Stage1_Portfolio_Choice_1007.docx](reports/stage1/Stage1_Portfolio_Choice_1007.docx).
The report was updated on 7 October 2026 and has four pages.
This repository contains the current 29-stock analysis, its frozen source data,
and the inputs needed to continue the project. Earlier 21/24-stock analyses and
exploratory downloads are omitted.

## Start here

Use Python **3.10 or newer**. From the repository root:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/reproduce_stage1.py
```

The default pipeline works **offline** with the included snapshot. It rebuilds
the seven corporate-action adjustments, prepares the monthly data, estimates all
portfolios, draws the three figures used in the current report, and runs independent numerical checks.
The current run's `validation/run.json` must report
`status: offline_reproduction_and_validation_passed`, and its final verification
receipt `validation/reproduction.json` must report `status: pass`. Check both;
an earlier successful verifier receipt alone does not certify a later failed
pipeline run. No Yahoo, French, GitHub, personal database, or
Word login is required for reproduction.

For an interactive walkthrough:

```bash
python -m pip install -r requirements-notebook.txt
python -m jupyter lab notebooks/stage1_walkthrough.ipynb
```

The edited PDF and Word file are reviewed document snapshots. Running the analysis regenerates
data, tables and figures; it does not rewrite either report file or its manual edits.

## Current scope

| Item | Definition |
|---|---|
| Cohort | DJIA members on 31 October 2015, with old E. I. du Pont excluded for an identity-consistent historical price gap |
| Assets | 29 USD stock return series; original UTX continues as RTX |
| Return window | November 2015–August 2026, 130 common monthly observations |
| Price baseline | October 2015 |
| Main portfolios | Unrestricted tangency, fixed value weights, long-only tangency |
| Time sensitivity | Full sample, first 65 months, second 65 months |
| Universe sensitivity | All 29, retained 23, and the six later DJIA removals |
| Value-weight date | Yahoo company market capitalization on 31 August 2026 |
| Factor / RF snapshot | Official US Fama–French 3-factor file, 202608 release |

The six later index removals are GE (2018-06-26), XOM/PFE/UTX–RTX
(2020-08-31), INTC (2024-11-08), and VZ (2026-06-29). Their returns remain in
the original cohort after index removal. **Index removal is not exchange
delisting.** Original membership, identity notes and official links are in
`data/evidence/roster_and_removals.json`.

## Results matching the report

Means and volatility below are **annualized arithmetic** percentages. Stock
summary statistics in Table 1.1 are **monthly** percentages.

| Portfolio / fitting window | Mean % | Volatility % | Model Sharpe | Gross % |
|---|---:|---:|---:|---:|
| All 29 tangency / full sample | 44.547 | 19.794 | 2.142 | 462.588 |
| Value weighted / full sample | 20.790 | 15.712 | 1.186 | 100.000 |
| Long only / full sample | 22.207 | 13.946 | 1.438 | 100.000 |
| First-half tangency / first half | 44.215 | 13.739 | 3.146 | 612.580 |
| Second-half tangency / second half | 84.477 | 23.051 | 3.521 | 772.765 |
| Retained 23 tangency / full sample | 40.144 | 18.350 | 2.071 | 376.473 |
| Later-removal 6 tangency / full sample | 17.298 | 20.907 | 0.725 | 102.224 |

The half-sample weight vectors have correlation 0.106 and 17 sign changes.
Applying first-half fitted weights to second-half returns gives model Sharpe
0.432. The 23-stock and six-stock portfolios are **independently re-estimated**,
not renormalized pieces of the 29-stock weights.

## Repository map

| Path | Purpose |
|---|---|
| `config/universe.json` | Ordered ticker list, date window, sources and current report metadata |
| `data/raw/` | Instructor prices; frozen Yahoo price, capitalization and action responses; official French CSV |
| `data/evidence/` | Historical roster, distribution terms and frozen event calculations |
| `data/processed/` | Nine prepared monthly data / audit tables |
| `tools/` | Portable preparation, estimation, plotting, acquisition and validation code |
| `results/stage1/` | Means, covariance, weights, portfolio returns, performance and figures |
| `results/stage1/universe_sensitivity/` | Re-estimated 29 / 23 / 6 portfolios |
| `validation/` | Frozen accepted numerical reference and newly generated check receipts |
| `notebooks/stage1_walkthrough.ipynb` | Executed companion to Exhibits 1a–1c and the subset comparisons |
| `reports/stage1/` | Latest reviewed four-page PDF and editable Word report |
| `docs/DATA_AND_METHODS.md` | Source priority, units, spin-off convention and calculation definitions |
| `docs/COLLABORATOR_HANDOFF.md` | Exact Stage 2 inputs and continuation instructions |

The raw snapshot is about 12 MB. Duplicate daily CSVs, obsolete analyses, THS
probes, personal database ingestion code, report-edit scratch files and browser
screenshots are excluded. The small instructor source file is preserved as
supplied; the current pipeline uses only its 15 overlapping cohort stocks.

## Report figures

The three current report comparisons are available as PNG and SVG:

| Report table | Figure |
|---|---|
| Table 1.2 Portfolio weights | `results/stage1/figures/exhibit_1b_three_portfolios` |
| Table 1.3 Time re-estimation | `results/stage1/figures/time_weights_three_dated` |
| Table 1.4 Universe re-estimation | `results/stage1/universe_sensitivity/figures/weights_three` |

The time legend identifies both 65-month estimation windows. The older
standalone six-stock chart remains available as supplementary material; it is
not part of the current report or the default walkthrough.
This update changes report wording, layout and figure presentation. The source
snapshot, portfolio estimates and accepted numerical reference are unchanged.

## Continue with Stage 2

Read [the handoff contract](docs/COLLABORATOR_HANDOFF.md) before joining tables.
The main inputs are:

- `data/processed/returns_us_monthly.csv`: 130 × 29 stock **raw simple returns**.
- `data/processed/ff3_monthly.csv`: aligned `Mkt-RF`, `SMB`, `HML`, `RF`.
- `results/stage1/exhibit_1b_weights.csv`: the three main weight vectors.
- `results/stage1/portfolio_monthly_returns.csv`: fixed-weight portfolio raw
  returns; use the aligned RF column in `ff3_monthly.csv` to obtain excess returns.

Use the `Month` key (`YYYY-MM`), verify a one-to-one join, and keep numbers in
decimal units: `0.01 = 1%`. Subtract RF **once** from raw portfolio returns;
`Mkt-RF` is already an excess return. All main portfolios are rebalanced to the
same fixed target weights monthly.

The source snapshot also supplies daily bars and action terms for later weekly
robustness work. **Weekly prepared returns and weekly factors are not included;
weekly robustness has not been performed.**

## Refreshing source data

Optional acquisition code is provided separately:

```bash
python tools/fetch_sources.py --output work/new_source_snapshot
```

This is the explicit network step. It writes to a new directory, never to the
frozen `data/raw` snapshot. Provider revisions can change historical adjusted
prices or factor releases. Review a new snapshot and its date coverage before
promoting it into a new analysis version; do not silently replace the accepted
reference or assume it still reproduces the current report.
The acquisition command's help and overwrite protections were checked; fresh
network acquisition was not run during this handoff.

## Validation and interpretation

The independent verifier reads the raw inputs, recomputes monthly returns and
factors, checks all seven action calculations, solves unrestricted portfolios
by a separate linear-algebra route, and checks long-only allocation with an
independent optimizer. It compares inputs and outputs with the frozen accepted
reference, not only with the newly generated files. Tolerances and measured
differences are recorded in `validation/reproduction.json`.

Model Sharpe uses raw portfolio-return volatility, matching the report and
covariance convention. A separately named realized-excess Sharpe uses excess
return volatility. These two fields are not interchangeable. Value weights are
fixed **sample-end** capitalizations, not a historical capitalization index.
The 23 / 6 status groups are selected ex post; their fitted comparison is not a
causal estimate of the effect of index removal. See the method notes for details.
