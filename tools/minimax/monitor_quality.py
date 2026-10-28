"""Sample resource use while the explicit local H3 comparison runs."""
import argparse
import json
from pathlib import Path
import subprocess
import time

import psutil
from download_assets import atomic_replace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report', type=Path, default=Path(r'C:\install\AI\Data\H3Quality20261018\run.json'))
report = parser.parse_args().report.resolve()
if not report.is_relative_to(Path(r'C:\install\AI\Data')):
    raise ValueError('The resource report must remain under central Data')
output = report.parent / 'resource-samples.json'
samples = json.loads(output.read_text(encoding='utf-8'))['samples'] if output.exists() else []
deadline = time.monotonic() + 3 * 60 * 60
while time.monotonic() < deadline:
    state = json.loads(report.read_text(encoding='utf-8'))
    raw = subprocess.run(['nvidia-smi', '--query-gpu=memory.total,memory.used,memory.free,utilization.gpu',
                          '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout.strip()
    total, used, free, utilization = [int(x.strip()) for x in raw.split(',')]
    memory = psutil.virtual_memory()
    samples.append({'time': time.time(), 'stage': state['stage'], 'totalVramMiB': total, 'usedVramMiB': used,
                    'freeVramMiB': free, 'gpuUtilizationPercent': utilization,
                    'systemAvailableMiB': round(memory.available / 1024**2)})
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps({'intervalSeconds': 2, 'samples': samples,
                                     'sampledPeakVramMiB': max(x['usedVramMiB'] for x in samples),
                                     'minimumSystemAvailableMiB': min(x['systemAvailableMiB'] for x in samples)}), encoding='utf-8')
    atomic_replace(temporary, output)
    if state['stage'] in ['ReadyForUserPreview', 'Failed', 'Blocked']:
        break
    time.sleep(2)
print(json.dumps({'samples': len(samples), 'sampledPeakVramMiB': max(x['usedVramMiB'] for x in samples)}))
