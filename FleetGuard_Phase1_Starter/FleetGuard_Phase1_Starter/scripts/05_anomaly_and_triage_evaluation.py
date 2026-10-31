"""Deprecated historical entry point; dispatch to the isolated Phase A runner.

The original source is preserved in the Phase A baseline snapshot. This command
never deletes the historical database or overwrites the old result summaries.
"""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("06_phase_a.py")), run_name="__main__")
