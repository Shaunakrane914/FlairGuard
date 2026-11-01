"""Run the bounded, versioned Phase D development study."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flairguard.phase_d.study import run
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(Path(__file__).resolve().parents[1],args.output)
