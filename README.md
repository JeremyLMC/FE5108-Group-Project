# FE5108 Group Project

Reproducible materials for the FE5108 group project, organized by stage. Each
stage keeps its inputs, analysis code, outputs, report and validation receipts
in its own folder.

## Start here

| Stage | Reviewed report | Analysis notebook | Package guide |
|---|---|---|---|
| Stage 1: Portfolio choice | [PDF](stage1/reports/stage1/Stage1_Portfolio_Choice_1007.pdf), [editable Word](stage1/reports/stage1/Stage1_Portfolio_Choice_1007.docx) | [Stage 1 walkthrough](stage1/notebooks/stage1_walkthrough.ipynb) | [Stage 1 README](stage1/README.md) |
| Stage 2: The CAPM | [PDF](stage2/reports/Stage2_CAPM_Report.pdf) | [Stage 2 analysis](stage2/stage2_analysis.ipynb) | [Stage 2 README](stage2/README.md) |

Stage 1 contains the reviewed 29-stock portfolio analysis and the frozen raw
snapshot used to prepare the monthly data. Stage 2 contains the completed CAPM
analysis based on its own frozen copies of the monthly stock-return and factor
tables. These are stage components; the remaining stages and final combined
submission are outside this handoff.

## Reproduce the analysis

Use a Python environment compatible with the requirements for the stage being
run. Stage 1 requires Python 3.10 or newer; Stage 2 records its tested environment
in its package guide and validation receipt. All commands below run from the
repository root.

For Stage 1:

```bash
python -m pip install -r stage1/requirements.txt
python stage1/tools/reproduce_stage1.py
```

For Stage 2:

```bash
python -m pip install -r stage2/requirements.txt
python stage2/run_stage2.py
```

For the interactive Stage 1 walkthrough:

```bash
python -m pip install -r stage1/requirements-notebook.txt
python -m jupyter lab stage1/notebooks/stage1_walkthrough.ipynb
```

The Stage 2 notebook can be opened in VS Code with the environment that has its
requirements installed. Both analysis pipelines use bundled inputs offline;
neither command rewrites the reviewed report snapshots. See each package guide
for its outputs, validation requirements and optional report-building steps.

## Data handoff between stages

The two Stage 2 inputs in `stage2/data/` are frozen copies of
`stage1/data/processed/returns_us_monthly.csv` and
`stage1/data/processed/ff3_monthly.csv`. Their contents match at this directory
reorganization. Stage 2 reads its own copies and does not automatically
synchronize them or read Stage 1 portfolio weights or portfolio results.

If stock returns, factors, sample membership, dates or cleaning conventions
change, review and synchronize the affected downstream inputs, rerun the
affected analysis, and update its validation and report. Changes only to Stage 1
report wording, figures or portfolio weights do not require the current Stage 2
analysis to be rerun. The detailed input dictionary and continuation notes are
in [the collaborator handoff](stage1/docs/COLLABORATOR_HANDOFF.md).
