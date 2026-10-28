"""Offline experimental eye-only residual adapter; official source and V1 stay intact."""
from pathlib import Path
import importlib.util,hashlib,json,sys

BASE=Path(__file__).resolve().parents[1]/'visual_pilot_acting/run.py'
BASE_SHA='f3a97f158443bcdb1f0b63cb4ed18f819959db89d068397a2428453069c60a83'
PROFILE='blink-residual-v1'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise RuntimeError('Frozen V1 engine changed')
spec=importlib.util.spec_from_file_location('frozen_acting_v1',BASE)
pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)
original_verify=pilot.verify_install;original_write=pilot.write_new
active=None
gain=1.0

def install():
    global gain
    if '--manifest' in sys.argv:
        request=json.loads(pilot.governed(sys.argv[sys.argv.index('--manifest')+1]).read_text(encoding='utf-8-sig'))
        gain=request.get('eyeResidualGain',1.0)
        if gain not in [1.0,1.5]:raise ValueError('Only frozen eye residual gains are allowed')
    result=original_verify()
    import src.live_portrait_pipeline as module
    if not getattr(module.LivePortraitPipeline,'_blink_residual_adapter',False):
        import numpy as np,cv2,torch
        from src.utils.retargeting_utils import calc_eye_close_ratio
        official=module.LivePortraitPipeline
        class BlinkPipeline(official):
            _blink_residual_adapter=True
            def __init__(self,*args,**kwargs):
                global active
                super().__init__(*args,**kwargs);active=self;self.rows=[];self.source_lmk=None;self.eyes=None;self.index=0
                source_crop=self.cropper.crop_source_image
                def crop(*a,**kw):
                    ret=source_crop(*a,**kw)
                    if ret is not None:self.source_lmk=ret['lmk_crop']
                    return ret
                self.cropper.crop_source_image=crop
                wrapper=self.live_portrait_wrapper;decode=wrapper.warp_decode
                def render(feature,kp_source,kp_driving):
                    baseline=decode(feature,kp_source,kp_driving)
                    i=self.index;self.index+=1
                    ratio=float(np.mean(self.eyes[i]));opened=float(np.percentile([np.mean(x) for x in self.eyes],90))
                    # Restrict changes to actual driver blink intervals, not every expression.
                    gate=float(np.clip((.75*opened-ratio)/max(.35*opened,.02),0,1))
                    row=dict(frame=i,driverEyeRatio=ratio,openReferenceRatio=opened,gate=gate,changed=False,outsideEyeMaxChange=0)
                    if gate>0 and self.source_lmk is not None:
                        image=wrapper.parse_output(baseline['out'])[0]
                        landmarks=self.cropper.calc_lmk_from_cropped_image(image)
                        if landmarks is None:raise RuntimeError('Cannot validate eye closure on generated crop')
                        current=float(calc_eye_close_ratio(landmarks[None]).mean());target=max(.015,ratio*.65)
                        row.update(baselineEyeRatio=current,targetEyeRatio=target)
                        if current>target+.01:
                            def eye_delta(value):
                                combined=wrapper.calc_combined_eye_ratio([[value]],self.source_lmk)
                                return wrapper.retarget_eye(kp_source,combined)
                            delta=eye_delta(target)-eye_delta(current)
                            keep=torch.zeros_like(delta);keep[:,[11,13,15,16,18],:]=delta[:,[11,13,15,16,18],:]
                            corrected=decode(feature,kp_source,kp_driving+torch.clamp(keep*gain,-.06,.06)*gate)
                            h,w=image.shape[:2];mask=np.zeros((h,w),np.float32)
                            for indexes in [range(0,24),range(24,48)]:
                                pts=landmarks[list(indexes)];lo=pts.min(0);hi=pts.max(0);cx,cy=(lo+hi)/2
                                rx=max(5,(hi[0]-lo[0])*.7);ry=max(4,(hi[1]-lo[1])*.95)
                                cv2.ellipse(mask,(round(cx),round(cy)),(round(rx),round(ry)),0,0,360,1,-1)
                            mask=cv2.GaussianBlur(mask,(5,5),.8)
                            alpha=torch.from_numpy(mask).to(baseline['out'].device)[None,None]
                            mixed=baseline['out']+alpha*(corrected['out']-baseline['out'])
                            if not torch.equal(mixed.expand_as(mixed)[alpha.expand_as(mixed)==0],baseline['out'][alpha.expand_as(mixed)==0]):
                                raise RuntimeError('Pixels outside the bounded eye masks changed')
                            baseline['out']=mixed
                            after_lmk=self.cropper.calc_lmk_from_cropped_image(wrapper.parse_output(mixed)[0])
                            row.update(changed=True,correctedEyeRatio=None if after_lmk is None else float(calc_eye_close_ratio(after_lmk[None]).mean()),eyeMaskPixels=int(np.count_nonzero(mask)))
                    self.rows.append(row)
                    return baseline
                wrapper.warp_decode=render
            def make_motion_template(self,images,eyes,lips,**kwargs):
                self.eyes=eyes
                return super().make_motion_template(images,eyes,lips,**kwargs)
        module.LivePortraitPipeline=BlinkPipeline
    result.update(repairProfile=PROFILE,eyeResidualGain=gain,baseEngineSha256=BASE_SHA,adapterSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result

def write(path,value):
    if value.get('gpuInferenceStarted') and value.get('provider'):
        if active is None or not active.rows or not any(r['changed'] for r in active.rows):raise RuntimeError('No real blink correction occurred')
        value.update(repairProfile=PROFILE,eyeCorrectionFrames=active.rows,
                     algorithm='Learned eye residual at driver blink times; full original motion retained; decoded eye masks only',
                     protectedPixels='Decoded 256x256 face-crop pixels outside eye masks exactly unchanged; pasteback/resampling and lossy encoding follow')
    original_write(path,value)

if __name__=='__main__':
    pilot.verify_install=install;pilot.write_new=write;pilot.main()
