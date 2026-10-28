"""Offline CPU speech transcript and audio-file checks for the three real WAVs."""
import hashlib,json,os,re,subprocess
from pathlib import Path
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['CUDA_VISIBLE_DEVICES']=''
from faster_whisper import WhisperModel

DATA=Path('C:/install/AI/Data');OUT=DATA/'CharacterPlotContinuation20261028';MODEL=Path('C:/install/AI/Models/ASR/faster-whisper-small')
FFMPEG=Path('C:/install/FFmpeg/bin/ffmpeg.exe');FFPROBE=Path('C:/install/FFmpeg/bin/ffprobe.exe')
EXPECTED_MODEL='3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671'
def hashfile(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def normalize(text):return re.sub(r'[^\u4e00-\u9fff0-9a-z]','',text.lower())

def main():
    state=json.loads((OUT/'run.json').read_text(encoding='utf-8'));assert hashfile(MODEL/'model.bin')==EXPECTED_MODEL
    assert all((MODEL/x).is_file() for x in ['config.json','tokenizer.json','vocabulary.txt'])
    model=WhisperModel(str(MODEL),device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True)
    rows=[]
    for entry in state['narration']:
        assert entry['status']=='Succeeded';path=DATA/entry['assetPath'];assert hashfile(path)==entry['sha256']
        probe=json.loads(subprocess.check_output([str(FFPROBE),'-v','error','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'))
        sound=next(s for s in probe['streams'] if s['codec_type']=='audio');duration=float(probe['format']['duration'])
        decode=subprocess.run([str(FFMPEG),'-hide_banner','-i',str(path),'-af','volumedetect','-f','null','-'],capture_output=True,text=True,timeout=120)
        assert decode.returncode==0 and duration>0.2
        volume=dict(re.findall(r'(mean_volume|max_volume):\s*([-\d.]+) dB',decode.stderr))
        assert len(volume)==2 and float(volume['max_volume'])<0 and float(volume['max_volume'])>-40
        segments,info=model.transcribe(str(path),language='zh',beam_size=5,vad_filter=False,condition_on_previous_text=False)
        result=''.join(x.text for x in segments)
        rows.append(dict(taskId=entry['taskId'],expected=entry['text'],recognized=result,exactNormalized=normalize(result)==normalize(entry['text']),durationSeconds=duration,startSeconds=entry['startSeconds'],sampleRate=sound['sample_rate'],codec=sound['codec_name'],volumeDb=volume))
    music=state['music'];path=DATA/music['assetPath'];assert music['status']=='Succeeded' and hashfile(path)==music['sha256']
    data=json.loads(subprocess.check_output([str(FFPROBE),'-v','error','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'))
    audio=next(s for s in data['streams'] if s['codec_type']=='audio')
    assert abs(float(data['format']['duration'])-15.5)<.001 and audio['channels']==2
    report=dict(technicalStatus='Passed',engine='Existing faster-whisper-small local CPU INT8',modelSha256=EXPECTED_MODEL,lines=rows,music=dict(taskId=music['taskId'],sha256=music['sha256'],durationSeconds=float(data['format']['duration']),codec=audio['codec_name'],sampleRate=audio['sample_rate'],channels=audio['channels']),contentStatus='NeedReview',note='ASR is a transcript cross-check only; voice quality, melody and mix still require listening.')
    (OUT/'audio-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
