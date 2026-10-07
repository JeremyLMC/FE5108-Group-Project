"""Reproduce Stage 1 offline from frozen sources and run independent checks.

Run from any working directory: python tools/reproduce_stage1.py
This updates numeric data/results/validation and the three main report figures.
It never edits the saved report, accesses a personal database, or issues a
network request.
"""
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import version
import json
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STEPS = ["audit_corporate_actions.py", "prepare_dow2015_inputs.py",
         "run_stage1_dow2015.py", "run_stage1_universe_sensitivity.py",
         "plot_stage1_portfolios_three.py", "plot_stage1_weights_three.py",
         "validate_reproduction.py"]


def main() -> None:
    missing = [name for name in STEPS if not (ROOT / "tools" / name).is_file()]
    if missing:
        raise FileNotFoundError("Incomplete reproduction checkout: " + ", ".join(missing))
    validation = ROOT / "validation"
    validation.mkdir(exist_ok=True)
    receipt = {"status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
               "python_version": platform.python_version(), "network_requests": 0,
               "report_files_modified": False, "steps": [],
               "packages": {name: version(name) for name in ("numpy", "pandas", "scipy", "matplotlib")}}
    def save() -> None:
        (validation / "run.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    save()
    try:
        for name in STEPS:
            print("Running " + name, flush=True)
            subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tools" / name)],
                           cwd=ROOT, check=True)
            receipt["steps"].append({"script": name, "status": "completed"})
            save()
        receipt["status"] = "offline_reproduction_and_validation_passed"
    except subprocess.CalledProcessError as error:
        receipt["status"] = "failed"
        receipt["failed_step"] = name
        receipt["exit_code"] = error.returncode
        raise
    finally:
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        save()
    print("Stage 1 offline reproduction and independent validation completed.")


if __name__ == "__main__":
    main()
