import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wildfire_researcher.notifications import run_monitor

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--once',action='store_true');p.add_argument('--test',action='store_true')
    args=p.parse_args();run_monitor(args.once,args.test)
