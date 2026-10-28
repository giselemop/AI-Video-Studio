"""Actual final decode, original voice equality, cut continuity and honest comparison."""
from run import *
import hashlib,cv2,numpy as np
from PIL import Image,ImageDraw
FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe';FFPROBE=r'C:\install\FFmpeg\bin\ffprobe.exe'
def probe(p):return json.loads(subprocess.check_output([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(p)]))
def frame(p,i):
    cap=cv2.VideoCapture(str(media(p)));cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,pixels=cap.read();cap.release()
    if not ok:raise RuntimeError('Missing actual comparison frame')
    return pixels
def inspect(p,w,h,fps,n,unique=False):
    path=media(p);result=subprocess.run([FFMPEG,'-nostdin','-v','error','-i',str(path),'-map','0:v:0','-f','null','-'],capture_output=True,text=True)
    if result.returncode or result.stderr.strip():raise RuntimeError('Complete video decode failed')
    info=probe(path);v=next(x for x in info['streams'] if x['codec_type']=='video');num,den=map(int,v['avg_frame_rate'].split('/'))
    if (v['width'],v['height'],int(v['nb_read_frames']))!=(w,h,n) or abs(num/den-fps)>.001 or abs(float(info['format']['duration'])-n/fps)>1/fps:raise RuntimeError('Actual output specification differs')
    value=dict(status='Passed',path=p,sha256=sha(path),width=w,height=h,fps=fps,frames=n,seconds=n/fps)
    if unique:
        cap=cv2.VideoCapture(str(path));hashes=[]
        while True:
            ok,pixels=cap.read()
            if not ok:break
            hashes.append(hashlib.sha256(pixels.tobytes()).hexdigest())
        cap.release()
        if len(hashes)!=n or len(set(hashes))!=n:raise RuntimeError('Final has duplicate or missing decoded frames')
        value['uniqueDecodedFrames']=len(set(hashes))
    return value
def audio(p,packets=True):
    args=['-c:a','copy','-f','data','pipe:1'] if packets else ['-f','s16le','-acodec','pcm_s16le','pipe:1']
    return subprocess.check_output([FFMPEG,'-v','error','-i',str(media(p)),'-map','0:a:0']+args)
def video_packets(p):return subprocess.check_output([FFMPEG,'-v','error','-i',str(media(p)),'-map','0:v:0','-c:v','copy','-f','data','pipe:1'])
