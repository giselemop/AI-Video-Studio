"""CPU-only local speech recognition, separate from GPU inference."""
import json
from pathlib import Path
import sys
import requests
import hashlib
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[2]
AI=ROOT.parent
FOLDER=AI/'Data/DialoguePilot20261023'
sys.path.insert(0,str(ROOT/'tools/minimax'))
from download_assets import download

if __name__=='__main__':
    repo='Systran/faster-whisper-small';revision='536b0662742c02347bc0e980a01041f333bce120'
    target=AI/'Models/ASR/faster-whisper-small'
    target.mkdir(parents=True,exist_ok=True)
    weight=target/'model.bin'
    expected='3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671'
    if not weight.exists():
        size=483546902;chunk=32*1024*1024
        slices=target/'download-slices';slices.mkdir(exist_ok=True)
        def fetch(i):
            start=i*chunk;end=min(size,start+chunk)-1
            part=slices/f'{i:03}.part'
            if part.exists() and part.stat().st_size==end-start+1:return part
            url=f'https://huggingface.co/{repo}/resolve/{revision}/model.bin?download=true&range_start={start}'
            with requests.get(url,headers={'Range':f'bytes={start}-{end}'},stream=True,timeout=(30,90)) as response:
                response.raise_for_status()
                if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{size}':raise RuntimeError('ASR range rejected')
                with part.open('wb') as f:
                    for data in response.iter_content(1024*1024):f.write(data)
            if part.stat().st_size!=end-start+1:raise RuntimeError('ASR range truncated')
            return part
        with ThreadPoolExecutor(max_workers=4) as pool:parts=list(pool.map(fetch,range(-(-size//chunk))))
        temp=target/'model.bin.verified-part'
        with temp.open('wb') as output:
            for part in parts:
                with part.open('rb') as f:
                    for data in iter(lambda:f.read(1024*1024),b''):output.write(data)
        with temp.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=expected:raise RuntimeError('ASR weight SHA mismatch')
        temp.rename(weight)
        print('Local ASR weights verified',flush=True)
    for file in ['config.json','tokenizer.json','vocabulary.txt']:
        if not (target/file).exists():
            r=requests.get(f'https://huggingface.co/{repo}/resolve/{revision}/{file}',timeout=60);r.raise_for_status()
            (target/file).write_bytes(r.content)
    from faster_whisper import WhisperModel
    model=WhisperModel(str(target),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    run=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    result=[]
    for i in range(1,5):
        expected=run['timeline'][i-1]['text']
        segments,info=model.transcribe(str(AI/'Data'/run[f'line{i}Path']),language='zh',beam_size=5,vad_filter=False,word_timestamps=True,condition_on_previous_text=False)
        items=[dict(text=s.text,start=s.start,end=s.end,avgLogprob=s.avg_logprob,words=[dict(word=w.word,start=w.start,end=w.end,probability=w.probability) for w in s.words or []]) for s in segments]
        result.append(dict(index=i,expected=expected,recognized=''.join(s['text'] for s in items),segments=items,languageProbability=info.language_probability))
    (FOLDER/'speech-audit.json').write_text(json.dumps(dict(engine='faster-whisper-small, CPU INT8, pinned local weights',status='NeedReview',note='ASR is evidence for transcript only; it does not certify speaker identity, emotion or lip synchronization.',lines=result),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
