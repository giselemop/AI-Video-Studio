"""Bounded sampled resource evidence for the authorized fresh video run."""
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from download_assets import atomic_replace

folder = ROOT.parent / 'Data/Qwen3Video20261022'
summary_path = folder / 'resource-summary.json'
summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {
    'intervalSeconds': 5, 'samples': 0, 'sampledPeakVramMiB': 0, 'minimumSystemAvailableMiB': None}
deadline = time.monotonic() + 14 * 60 * 60
while time.monotonic() < deadline:
    state = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    raw = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], encoding='utf-8')
    used, free, utilization = [int(v.strip()) for v in raw.strip().split(',')]
    sample = {'epochSeconds': time.time(), 'stage': state['stage'], 'usedVramMiB': used, 'freeVramMiB': free,
        'gpuUtilizationPercent': utilization, 'systemAvailableMiB': round(psutil.virtual_memory().available / 1024**2)}
    with (folder / 'resource-samples.jsonl').open('a', encoding='utf-8') as output: output.write(json.dumps(sample) + '\n')
    summary['samples'] += 1; summary['latest'] = sample
    summary['sampledPeakVramMiB'] = max(summary['sampledPeakVramMiB'], used)
    old = summary['minimumSystemAvailableMiB']
    summary['minimumSystemAvailableMiB'] = min(old, sample['systemAvailableMiB']) if old is not None else sample['systemAvailableMiB']
    temporary = summary_path.with_suffix('.tmp'); temporary.write_text(json.dumps(summary, indent=2), encoding='utf-8'); atomic_replace(temporary, summary_path)
    if state['stage'] in ['ReadyForUserPreview', 'AwaitingPlaybackInspection', 'Failed', 'Blocked']: break
    time.sleep(5)
print(json.dumps(summary), flush=True)
