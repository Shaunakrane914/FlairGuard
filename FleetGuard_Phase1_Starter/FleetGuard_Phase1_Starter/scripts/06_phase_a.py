"""Create a new isolated Phase A run; never overwrite a prior run."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flairguard.phase_a import run_phase_a
from flairguard.evidence import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,default=ROOT/'configs/phase_a_fd001_v1.json')
    parser.add_argument('--data-dir',type=Path,default=ROOT/'data/raw')
    parser.add_argument('--run-dir',type=Path,default=None)
    args=parser.parse_args()
    run=args.run_dir or ROOT/'artifacts/phase_a'/datetime.now(timezone.utc).strftime('fd001-v1-%Y%m%dT%H%M%SZ')
    if run.exists():
        parser.error('Run directory already exists; choose a new version. Resume/overwrite is deliberately unsupported.')
    try:
        run_phase_a(args.protocol,args.data_dir,run)
    except Exception as exc:
        if run.exists():
            write_json(run/'FAILED.json',dict(error_type=type(exc).__name__,error=str(exc),
                       status='TECHNICAL_FAILURE; no scientific success claim'))
        raise
    print('Saved evidence:',run)


if __name__=='__main__':
    main()
