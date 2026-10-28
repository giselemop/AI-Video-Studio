"""Offline semantic mouth-motion transfer with independently preserved approved pose."""
from pathlib import Path
import importlib.util,hashlib,json,sys,copy
BASE=Path(__file__).resolve().parents[1]/'dialogue_visual/acting.py'
BASE_SHA='8c480165e33b618a9eafc7db86e0008529281f916f3e64b3cdff0b5fe73d7347'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise RuntimeError('Validated portrait engine changed')
spec=importlib.util.spec_from_file_location('hybrid_validated_dialogue',BASE);actor=importlib.util.module_from_spec(spec);spec.loader.exec_module(actor)
original_verify=actor.verify_install;original_sink=actor._original_write
PROFILE='dialogue-hybrid-v1';LIPS=[6,12,14,17,19,20];request={};active=None
def install():
    global request
    result=original_verify();request=actor._dialogue_request
    if '--manifest' in sys.argv:
        pose=actor.governed(request['posePath'])
        if pose.suffix.lower()!='.mp4' or actor.sha(pose)!=request['poseSha256']:raise ValueError('Bound pose video changed')
        if request['faceDirection'] not in ['left-right','right-left'] or request['durationSeconds']!=57/25 or request.get('drivingMultiplier')!=1 or request.get('animationRegion')!='all':raise ValueError('Fixed dual-person hybrid profile required')
        info=actor.probe(pose);v=next(x for x in info['streams'] if x['codec_type']=='video')
        if int(v['nb_read_frames'])!=57 or v['avg_frame_rate']!='25/1':raise ValueError('Pose must match57frames25fps')
    import src.live_portrait_pipeline as module
    if not getattr(module.LivePortraitPipeline,'_hybrid_adapter',False):
        import cv2,numpy as np
        Parent=module.LivePortraitPipeline
        class Hybrid(Parent):
            _hybrid_adapter=True
            def __init__(self,*args,**kwargs):
                global active
                cfg=kwargs.get('inference_cfg',args[0] if args else None);cfg.flag_normalize_lip=True
                super().__init__(*args,**kwargs);active=self;self.hybrid_rows=[]
            def make_motion_template(self,images,eyes,lips,**kwargs):
                audio=super().make_motion_template(images,eyes,lips,**kwargs)
                cap=cv2.VideoCapture(request['posePath']);frames=[]
                while True:
                    ok,frame=cap.read()
                    if not ok:break
                    frames.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                cap.release()
                if len(frames)!=57:raise RuntimeError('Pose full decode differs')
                crop=self.cropper.crop_driving_video(frames);pose_eyes,pose_lips=self.live_portrait_wrapper.calc_ratio(crop['lmk_crop_lst'])
                prepared=self.live_portrait_wrapper.prepare_videos([cv2.resize(x,(256,256)) for x in crop['frame_crop_lst']])
                pose=super().make_motion_template(prepared,pose_eyes,pose_lips,**kwargs)
                if audio['n_frames']!=57 or pose['n_frames']!=57:raise RuntimeError('Hybrid timelines differ')
                result=copy.deepcopy(pose);keep=[i for i in range(21) if i not in LIPS]
                for i,(a,p,out) in enumerate(zip(audio['motion'],pose['motion'],result['motion'])):
                    delta=a['exp'][:,LIPS,:]-audio['motion'][0]['exp'][:,LIPS,:]
                    if float(np.max(np.abs(delta)))>.15:raise RuntimeError('Mouth motion exceeds bounded pilot range')
                    out['exp'][:,LIPS,:]=pose['motion'][0]['exp'][:,LIPS,:]+delta
                    if not np.array_equal(out['exp'][:,keep,:],p['exp'][:,keep,:]) or any(not np.array_equal(out[k],p[k]) for k in ['R','t','scale','kp','x_s']):raise RuntimeError('Approved pose/non-lip expression fields changed')
                    self.hybrid_rows.append(dict(frame=i,poseFieldsMaxChange=0,nonLipExpressionMaxChange=0,lipResidualMaxAbs=float(np.max(np.abs(delta)))))
                self.eyes=pose_eyes;result['c_lip_lst']=audio['c_lip_lst']
                return result
        module.LivePortraitPipeline=Hybrid
    result.update(repairProfile=PROFILE,hybridBaseEngineSha256=BASE_SHA,lipKeypointIndices=LIPS,sourceLipNormalized=True)
    return result
def sink(path,value):
    value.update(repairProfile=PROFILE,hybridBaseEngineSha256=BASE_SHA,lipKeypointIndices=LIPS,sourceLipNormalized=True)
    if value.get('gpuInferenceStarted'):
        if active is None or len(active.hybrid_rows)!=57 or actor.sha(actor.governed(request['posePath']))!=request['poseSha256']:raise RuntimeError('Hybrid pose trace/hash incomplete')
        value.update(posePath=request['posePath'],poseSha256=request['poseSha256'],hybridMotionFrames=active.hybrid_rows,
            hybridMotionScope='R/t/scale and non-lip expression entries exactly from approved pose driver; fresh audio lip entries only. This is a latent-motion assertion, not decoded-pixel invariance.')
    original_sink(path,value)
if __name__=='__main__':
    actor.verify_install=install;actor._original_write=sink;actor.main()
