"""Read-only story progress; never creates or retries tasks."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import time

import requests

FOLDER = Path(r'C:\install\AI\Data\H3CampusStory20261021')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--wait', type=int, choices=range(0, 56), default=0)
args = parser.parse_args()
time.sleep(args.wait)
s = requests.Session()
s.trust_env = False
state = json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
items = []
for n in range(1, 6):
    task_id = state.get(f'shot{n}TaskId')
    if task_id:
        detail = s.get(f'http://127.0.0.1:18080/api/tasks/{task_id}', timeout=15).json()['task']
        items.append({k: detail.get(k) for k in ['id', 'status', 'durationMs', 'vramPeakMiB', 'errorMessage']})
queue = s.get('http://127.0.0.1:8188/queue', timeout=15).json()
log = Path(r'C:\install\AI\VideoStudio\logs\native1080-20261019\comfy.stderr.log').read_text(encoding='utf-8', errors='replace').split('got prompt')[-1]
progress = re.findall(r'(\d+)/20\s+\[([^\]]+)\]', re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', log))
resource = json.loads((FOLDER/'resource-summary.json').read_text(encoding='utf-8'))
print(json.dumps({'time': datetime.now().isoformat(), 'stage': state['stage'], 'tasks': items,
    'comfyRunning': len(queue['queue_running']), 'comfyPending': len(queue['queue_pending']),
    'sampler': progress[-1] if progress else None, 'resources': resource['latest']}, ensure_ascii=True))
