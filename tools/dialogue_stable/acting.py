"""Local fixed-shot lip/pose separation and deterministic blink control.

Existing validated runners and weights stay immutable. These assertions concern
latent controls; decoded appearance is checked separately before selection.
"""
from pathlib import Path
import importlib.util,hashlib,json,sys,copy
BASE=Path(__file__).resolve().parents[1]/'dialogue_visual/acting.py'
BASE_SHA='8c480165e33b618a9eafc7db86e0008529281f916f3e64b3cdff0b5fe73d7347'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise RuntimeError('Validated engine changed')
spec=importlib.util.spec_from_file_location('stable_dialogue_base',BASE)
actor=importlib.util.module_from_spec(spec);spec.loader.exec_module(actor)
original_verify=actor.verify_install;original_sink=actor._original_write
PROFILE='dialogue-stable-v1';LIPS=[6,12,14,17,19,20];EYES=[11,13,15,16,18]
request={};active=None
SCHEDULES={'female-close':(57,'large-small',25),'male-close':(46,'large-small',13),
           'female-wide':(151,'left-right',100),'male-wide':(151,'right-left',130)}

def install():
    global request
    result=original_verify();request=actor._dialogue_request
    if '--manifest' in sys.argv:
        n,direction,centre=SCHEDULES[request['stableRole']]
        pose=actor.governed(request['posePath'])
        if actor.sha(pose)!=request['poseSha256'] or pose.suffix.lower()!='.mp4':raise ValueError('Pose hash/type changed')
        v=next(x for x in actor.probe(pose)['streams'] if x['codec_type']=='video')
        if int(v['nb_read_frames'])!=n or v['avg_frame_rate']!='25/1' or request['durationSeconds']!=n/25 or request['faceDirection']!=direction or request['animationRegion']!='all' or request['drivingMultiplier']!=1:raise ValueError('Fixed stable role/timeline required')
    import src.live_portrait_pipeline as module
    import cv2,numpy as np
    Parent=module.LivePortraitPipeline
    class Stable(Parent):
        def __init__(self,*args,**kwargs):
            global active
            cfg=kwargs.get('inference_cfg',args[0] if args else None);cfg.flag_normalize_lip=True
            super().__init__(*args,**kwargs);active=self;self.control_rows=[]
        def make_motion_template(self,images,eyes,lips,**kwargs):
            audio=super().make_motion_template(images,eyes,lips,**kwargs)
            n,direction,centre=SCHEDULES[request['stableRole']]
            cap=cv2.VideoCapture(request['posePath']);frames=[]
            while True:
                ok,frame=cap.read()
                if not ok:break
                frames.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            cap.release()
            if len(frames)!=n:raise RuntimeError('Pose decode count differs')
            crop=self.cropper.crop_driving_video(frames)
            pe,pl=self.live_portrait_wrapper.calc_ratio(crop['lmk_crop_lst'])
            pv=self.live_portrait_wrapper.prepare_videos([cv2.resize(x,(256,256)) for x in crop['frame_crop_lst']])
            pose=super().make_motion_template(pv,pe,pl,**kwargs)
            if pose['n_frames']!=n or audio['n_frames']!=n:raise RuntimeError('Motion timeline differs')
            result=copy.deepcopy(pose);controlled=[]
            for i,(a,p,out) in enumerate(zip(audio['motion'],pose['motion'],result['motion'])):
                delta=a['exp'][:,LIPS,:]-audio['motion'][0]['exp'][:,LIPS,:]
                if float(np.max(np.abs(delta)))>.15:raise RuntimeError('Lip residual out of validated range')
                out['exp'][:,LIPS,:]=pose['motion'][0]['exp'][:,LIPS,:]+delta
                # Remove random driver eye closures. Source eyes are preserved;
                # the existing learned eye residual supplies the single blink.
                out['exp'][:,EYES,:]=pose['motion'][0]['exp'][:,EYES,:]
                if any(not np.array_equal(out[k],p[k]) for k in ['R','t','scale','kp','x_s']):raise RuntimeError('Pose fields changed')
                closure={-3:0,-2:.35,-1:.8,0:1,1:.8,2:.35,3:0}.get(i-centre,0)
                ratio=.30*(1-closure)+.015*closure
                controlled.append(np.full_like(pe[i],ratio))
                self.control_rows.append(dict(frame=i,poseFieldsMaxChange=0,eyeExpressionDeltaMax=0,lipResidualMaxAbs=float(np.max(np.abs(delta))),scheduledClosure=closure))
            self.eyes=controlled;result['c_eyes_lst']=controlled;result['c_lip_lst']=audio['c_lip_lst']
            return result
    module.LivePortraitPipeline=Stable
    result.update(repairProfile=PROFILE,stableRoles=list(SCHEDULES),baseEngineSha256=BASE_SHA)
    return result

def sink(path,value):
    value.update(repairProfile=PROFILE,baseEngineSha256=BASE_SHA,sourceLipNormalized=True)
    if value.get('gpuInferenceStarted'):
        n,_,centre=SCHEDULES[request['stableRole']]
        if active is None or len(active.control_rows)!=n or actor.sha(actor.governed(request['posePath']))!=request['poseSha256']:raise RuntimeError('Stable trace incomplete')
        value.update(stableRole=request['stableRole'],poseSha256=request['poseSha256'],controlledMotionFrames=active.control_rows,blinkCentreFrame=centre,
                     controlScope='Approved pose fields; fresh existing audio lip residual; frozen semantic eyes and one scheduled eye-mask residual. Static body outside face support.')
    original_sink(path,value)

if __name__=='__main__':
    actor.verify_install=install;actor._original_write=sink;actor.main()
