"""A second offline transcript check with the known story context."""
import json,os
from pathlib import Path
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['CUDA_VISIBLE_DEVICES']=''
from faster_whisper import WhisperModel
DATA=Path('C:/install/AI/Data');OUT=DATA/'CharacterPlotContinuation20261028';MODEL=Path('C:/install/AI/Models/ASR/faster-whisper-small')

def main():
    s=json.loads((OUT/'run.json').read_text(encoding='utf-8'));model=WhisperModel(str(MODEL),device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True)
    rows=[]
    for e in s['narration']:
        segments,_=model.transcribe(str(DATA/e['assetPath']),language='zh',beam_size=5,vad_filter=False,condition_on_previous_text=False,initial_prompt='故事发生在午后，林安在窗边等待朋友，朋友到来后她微笑回应。')
        rows.append(dict(taskId=e['taskId'],expected=e['text'],recognized=''.join(x.text for x in segments)))
    report=dict(engine='Existing faster-whisper-small CPU, with story context',lines=rows,note='Context can bias recognition; speech and emotional delivery still require human listening.')
    (OUT/'audio-context-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
