"""Run the bounded FD003/FD004 secondary diagnostic into a fresh output directory."""
from pathlib import Path
import argparse
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from flairguard.coverage_study import run_study

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matlab", type=Path)
    args = parser.parse_args()
    print(run_study(PROJECT, args.output, args.matlab))
