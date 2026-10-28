"""Publish a read-only comparison of the original and registered repair."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from character_turn_repair import ROOT,OUT,sha,write

def run():
    state=json.loads((OUT/'run.json').read_text(encoding='utf-8'));attempt=state['attempts'][-1]
    if not attempt.get('taskId'):raise RuntimeError('No registered repair task')
    manifest=dict(baseTaskId=state['baseTaskId'],source=state['source'],attempts=state['attempts'],contentReview='NeedReview',publication='Blocked')
    payload=json.dumps(manifest,ensure_ascii=False).replace('<','\\u003c')
    template=(ROOT/'tools/character_turn_review.template.html').read_text(encoding='utf-8');text=template.replace('__PAYLOAD__',payload)
    for folder in [ROOT/'web/public',ROOT/'web/dist']:(folder/'character-turn-repair.html').write_text(text,encoding='utf-8')
    write(OUT/'preview-page.json',dict(url='http://127.0.0.1:18080/character-turn-repair.html',sha256=sha(ROOT/'web/public/character-turn-repair.html'),taskId=attempt['taskId'],baseTaskId=state['baseTaskId']))
    print('Real original and targeted repair comparison page created; content remains NeedReview.')
if __name__=='__main__':run()
