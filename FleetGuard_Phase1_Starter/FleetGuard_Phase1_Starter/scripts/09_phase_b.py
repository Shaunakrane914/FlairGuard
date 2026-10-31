"""Run the frozen FD002 experiment into a new, isolated version directory."""
import argparse
from pathlib import Path
from datetime import datetime,timezone
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flairguard.phase_b import run_phase_b
from flairguard.evidence import write_json

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,default=ROOT/'configs/phase_b_fd002_v1.json')
    parser.add_argument('--data-dir',type=Path,default=ROOT/'data/raw')
    parser.add_argument('--run-dir',type=Path)
    args=parser.parse_args();run=args.run_dir or ROOT/'artifacts/phase_b'/datetime.now(timezone.utc).strftime('fd002-v1-%Y%m%dT%H%M%SZ')
    if run.exists():parser.error('Existing outputs are protected; use a fresh run directory')
    try:run_phase_b(args.protocol,args.data_dir,run)
    except Exception as error:
        if run.exists():write_json(run/'FAILED.json',dict(status='TECHNICAL_FAILURE',error_type=type(error).__name__,error=str(error)))
        raise
    print('Saved FD002 evidence:',run)
