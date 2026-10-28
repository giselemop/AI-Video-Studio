"""Read the recorded task, queue, sampler log and sampled resources without submitting work."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import requests

FOLDER = Path(r'C:\install\AI\Data\H3Refined108020261020')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait', type=int, default=0, choices=range(56))
    args = parser.parse_args()
    time.sleep(args.wait)
    state = json.loads((FOLDER / 'run.json').read_text(encoding='utf-8'))
    session = requests.Session()
    session.trust_env = False
    response = session.get('http://127.0.0.1:18080/api/tasks/' + str(state['taskId']), timeout=10)
    response.raise_for_status()
    task = response.json()['task']
    queue = session.get('http://127.0.0.1:8188/queue', timeout=10).json()
    log = Path(r'C:\install\AI\VideoStudio\logs\native1080-20261019\comfy.stderr.log').read_bytes().decode('utf-8', errors='replace')
    log = re.sub(r'\x1b\[[0-9;]*m', '', log.split('got prompt')[-1])
    steps = re.findall(r'(\d+)/20\s+\[([^\]]+)\]', log)
    resources = json.loads((FOLDER / 'resource-samples.json').read_text(encoding='utf-8'))
    started = datetime.fromisoformat(task['startedAt']).replace(tzinfo=timezone.utc)
    # The service exposes local Asia/Shanghai wall time without an offset.
    from datetime import timedelta
    elapsed = (datetime.now(timezone.utc) - (started - timedelta(hours=8))).total_seconds()
    result = {'updatedUtc': datetime.now(timezone.utc).isoformat(),
              'taskId': task['id'], 'status': task['status'], 'progress': task.get('progress'),
              'elapsedMinutes': round(elapsed / 60, 1), 'error': task.get('errorMessage'),
              'samplerStep': steps[-1] if steps else None,
              'comfyRunning': len(queue['queue_running']), 'comfyPending': len(queue['queue_pending']),
              'latestResources': resources['samples'][-1],
              'sampledPeakVramMiB': resources['sampledPeakVramMiB'],
              'minimumSystemAvailableMiB': resources['minimumSystemAvailableMiB'],
              'logTail': log[-220:]}
    (FOLDER / 'live-status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
