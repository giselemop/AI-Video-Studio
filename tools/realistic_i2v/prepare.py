"""Prepare the pinned SDXL reference model; reuse the existing ComfyUI runtime."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/minimax'))
from download_assets import download,download_lock

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workers',type=int,choices=range(1,9),default=8)
    parser.add_argument('--pose',action='store_true',help='Prepare the separately pinned SDXL OpenPose ControlNet')
    args=parser.parse_args()
    config=json.loads((ROOT/('config/realistic-pose-assets.json' if args.pose else 'config/realistic-reference-assets.json')).read_text(encoding='utf-8'))
    models=ROOT.parent/'Models'
    with download_lock(models,'.realvis-pose-download.lock' if args.pose else '.realvis-download.lock','Another reference model preparation is active'):
        download(config,models,workers=args.workers,chunk_size=16*1024**2)
        (models/config['target']).with_suffix('.deployment.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='Passed',model=config['target'],revision=config['revision'])),flush=True)

if __name__=='__main__':main()
