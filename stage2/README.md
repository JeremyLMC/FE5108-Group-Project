# Stage 2 The CAPM

Track A, Stage 2, FE5108 midterm group project. All Stage 2 materials are in this folder. The final report is `reports/Stage2_CAPM_Report.pdf` (four pages). Its structure and restrained presentation follow the Stage 1 report.

## Requirements and completed exhibits

| Handout requirement | Implementation | Report |
|---|---|---|
| 2a: beta, alpha, alpha t statistic, R squared for each asset | `results/capm_results.csv` | Table 2.1, p. 1 |
| 2b: average excess return versus estimated beta, fitted and theoretical SML | `figures/empirical_sml.png`, `results/sml_points.csv`, `results/sml_summary.csv` | Figure 2.1, p. 2 |
| 2c: joint assessment of zero alphas, allowing chance-count discussion | `results/alpha_tests.csv`, `results/alpha_assessment.csv` | Tables 2.3 and 2.4, p. 3 |
| 2d: fitted slope and intercept versus theory, with interpretation | `results/sml_comparison.csv`, `results/pricing_deviations.csv` | Table 2.5 and discussion, p. 4 |

Original inspection: the desktop Stage 2 folder contained an 11-cell notebook, five result CSVs and an SML chart. Exhibits 2a-2c were present; 2d, a formal report, a standalone reproduction entry point and package documentation were missing. Existing numeric outputs were verified before completing them. The methods remain ordinary OLS and the handout's approximate `|t| > 2` criterion; no Holm adjustment or GRS test is added.

## Reproduce

From the repository root: `python stage2/run_stage2.py`

From this folder: `python run_stage2.py`

Alternatively, open `stage2_analysis.ipynb` in VS Code, select the project's Python environment and Run All. The notebook is self-contained within this folder and retains the step-by-step 2a-2c work, then adds 2d.

Dependencies and tested versions: Python 3.13.16; see `requirements.txt` and `validation/reproduction.json`. The command regenerates every analytical exhibit from the two bundled cleaned inputs; report layout is regenerated separately by `build_report.py` with ReportLab and pandas. The report builder needs only reportlab, pandas and the generated outputs. It does not require a data download.

## Data provenance and conventions

- `data/returns_us_monthly.csv`: unchanged frozen Stage 1 return panel, 130 monthly USD observations (November 2015-August 2026), 29 original October 2015 DJIA members. Old DuPont is excluded; UTX continues as RTX; later index removals remain in the universe. Instructor prices have priority for covered ordinary months; Yahoo provides extensions and other series. Seven mandatory spin-off months use the documented Stage 1 reinvestment convention. Full raw data and cleaning code remain in the sibling Stage 1 package at `../stage1/data/`, `../stage1/tools/` and [its data and methods guide](../stage1/docs/DATA_AND_METHODS.md).
- `data/ff3_monthly.csv`: unchanged Stage 1 Kenneth French monthly factors (202608 vintage). All columns are already decimals, converted from published percent units once. RF is the one-month Treasury-bill proxy. Mkt-RF is the broad US equity market excess return, not the value-weighted 29-stock Stage 1 portfolio. SMB and HML are not used in Stage 2.
- Subtract the contemporaneous RF once from each stock return. Do not subtract RF again from Mkt-RF or divide either input by 100 again.
- Alpha, SML intercept and slope are monthly decimal returns in CSVs; tables and plots display percentages. Beta and R squared are unitless. Time-series inference uses conventional OLS standard errors.
- Stage 2 reproduces from cleaned Stage 1 inputs. Raw-to-clean reproduction belongs to the Stage 1 pipeline; this standalone folder does not claim to reconstruct raw corporate-action data. No new raw downloads or cleaning changes were made.

The two files in `data/` currently have the same contents as
`../stage1/data/processed/returns_us_monthly.csv` and
`../stage1/data/processed/ff3_monthly.csv`. Stage 2 reads these local frozen
copies; they are not synchronized automatically. It does not read Stage 1
portfolio weights or portfolio results. If stock returns, factors, sample
membership, dates or cleaning conventions change, review and synchronize the
affected downstream inputs, rerun the affected analysis, and update its
validation and report. Changes only to Stage 1 report wording, figures or
portfolio weights do not require the current Stage 2 analysis to be rerun.

## Verification

`validation/reproduction.json` records package versions, SHA256 hashes and numerical checks. `validation/existing_results_comparison.json` checks the original desktop CSVs against the new run. `validation/notebook_execution.json` verifies notebook code cells execute top to bottom. `validation/report_review.json` records four-page PDF and visual review checks.

The four-page report is a Stage 2 component for integration into the group's final report, not the whole project submission. The final combined report still needs the handout's one-page executive summary, Stages 3-4, signed contribution statement and overall page-limit check. AI acknowledgement wording for the final appendix is in `AI_ACKNOWLEDGEMENT.txt`.
