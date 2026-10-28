"""Append low-overhead local resource samples while the existing story tasks run."""
import json
from pathlib import Path
import subprocess
import time

import psutil
from download_assets import atomic_replace

FOLDER = Path(r'C:\install\AI\Data\H3CampusStory20261021')
summary_path = FOLDER / 'resource-summary.json'
summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {
    'intervalSeconds': 5, 'samples': 0, 'sampledPeakVramMiB': 0, 'minimumSystemAvailableMiB': None}
deadline = time.monotonic() + 36 * 60 * 60
while time.monotonic() < deadline:
    state = json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    raw = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu',
                          '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout.strip()
    used, free, utilization = [int(x.strip()) for x in raw.split(',')]
    sample = {'time': time.time(), 'stage': state['stage'], 'usedVramMiB': used, 'freeVramMiB': free,
              'gpuUtilizationPercent': utilization, 'systemAvailableMiB': round(psutil.virtual_memory().available/1024**2)}
    with (FOLDER/'resource-samples.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(sample) + '\n')
    summary['samples'] += 1
    summary['sampledPeakVramMiB'] = max(summary['sampledPeakVramMiB'], used)
    previous = summary['minimumSystemAvailableMiB']
    summary['minimumSystemAvailableMiB'] = min(previous, sample['systemAvailableMiB']) if previous is not None else sample['systemAvailableMiB']
    summary['latest'] = sample
    temporary = summary_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    atomic_replace(temporary, summary_path)
    if state['stage'] in ['ReadyForUserPreview', 'Failed', 'Blocked']:
        break
    time.sleep(5)
print(json.dumps(summary))
