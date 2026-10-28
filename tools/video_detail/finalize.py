"""Mark the review preview ready only after real output and browser checks pass."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/minimax'))
from run_local_acceptance import Acceptance
FOLDER=ROOT.parent/'Data/SeedVR2Enhancement20261022'

run=Acceptance('http://127.0.0.1:18080',FOLDER/'run.json')
run.access()
for name in ['output-verification.json','api-regression.json','browser-sample.json','browser-full.json']:
    if json.loads((FOLDER/name).read_text(encoding='utf-8'))['status']!='Passed':raise RuntimeError('Required check failed: '+name)
for key in ['exportTaskId','sampleExportTaskId','sampleRestoreTaskId','fullRestoreTaskId','sampleFinalTaskId','fullFinalTaskId']:
    if run.api(f'/api/tasks/{run.state[key]}')['task']['status']!='Succeeded':raise RuntimeError('Actual task is not successful')
run.save('ReadyForUserPreview',technicalStatus='Passed',codeValidation='Passed',error=None,
    finalVideoPath=run.state['fullFinalTaskIdPath'],finalVideoSha256=run.state['fullFinalTaskIdSha256'],
    previewUrl='http://127.0.0.1:18080/video-detail-compare.html',contentStatus='NeedReview',publicationStatus='Blocked')
print(json.dumps(dict(status='Passed',finalTaskId=run.state['fullFinalTaskId'],newTaskSubmitted=False)),flush=True)
