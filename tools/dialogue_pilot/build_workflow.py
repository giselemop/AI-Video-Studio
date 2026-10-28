"""Build audited InfiniteTalk graphs and append their experimental contracts."""
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image
from bootstrap import ASSETS

ROOT=Path(__file__).resolve().parents[2]
AI=ROOT.parent
DATA=AI/'Data/DialoguePilot20261023'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def build(frames):
    def node(cls,**inputs):return dict(class_type=cls,inputs=inputs)
    positive=('A natural live-action conversation between the same two East Asian adults sitting beside each other on a cream sofa. '
      'The woman on the LEFT wears a beige knitted cardigan and cream blouse, long wavy dark hair. '
      'The man on the RIGHT wears an olive green cardigan and dark T-shirt, short black hair and light stubble. '
      'Both adult faces remain visible in three-quarter view, looking toward each other. '
      'They alternate speaking Mandarin according to their own audio tracks. The woman smiles and teases him; '
      'the man replies with playful mock indignation and then a relaxed smile. '
      'The listener remains quiet, listens attentively and responds with a subtle smile. '
      'Natural synchronized lips, subtle eyebrows, gentle small head movements. '
      'Fixed camera, stable identities and clothes, realistic skin, warm afternoon window light, quiet living room. '
      'Keep hands resting on laps. No touching, no standing, no exaggerated laughter, no large gestures, no cuts.')
    negative='cartoon, doll, plastic skin, overexposure, blurry face, duplicated people, merged bodies, deformed mouth, huge open mouth, extra teeth, talking in unison, extra people, face morphing, identity change, head turn away, hand gestures, camera movement, text, watermark'
    graph={
      '1':node('LoadImage',image='pilot-reference.png'),
      '2':node('LoadAudio',audio='female-9.64s.wav'),
      '3':node('LoadAudio',audio='male-9.64s.wav'),
      '4':node('VideoStudioDialogueSpeakerMasks',image=['1',0],split_ratio=.38),
      '5':node('VideoStudioNativeWanTextCached',model_name='umt5_xxl_fp8_e4m3fn_scaled.safetensors',positive=positive,negative=negative),
      '6':node('Wav2VecModelLoader',model='wav2vec2-chinese-base_fp16.safetensors',base_precision='fp16',load_device='offload_device'),
      '7':node('MultiTalkWav2VecEmbeds',wav2vec_model=['6',0],audio_1=['2',0],audio_2=['3',0],normalize_loudness=False,num_frames=frames,fps=25.0,audio_scale=1.0,audio_cfg_scale=1.0,multi_audio_type='para',ref_target_masks=['4',0],add_noise_floor=False,smooth_transients=False),
      '8':node('MultiTalkModelLoader',model='Wan2_1-InfiniteTalk_Multi_Q8.gguf'),
      '9':node('VideoStudioAudioModelAfterText',model=['8',0],text=['5',0]),
      '10':node('WanVideoBlockSwap',blocks_to_swap=30,offload_img_emb=True,offload_txt_emb=True,use_non_blocking=False,vace_blocks_to_swap=0,prefetch_blocks=0,block_swap_debug=False),
      '11':node('WanVideoLoraSelect',lora='lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors',strength=1.0,low_mem_load=True,merge_loras=False),
      '12':node('WanVideoModelLoader',model='wan2.1-i2v-14b-480p-Q4_K_M.gguf',base_precision='bf16',quantization='disabled',load_device='offload_device',attention_mode='sdpa',block_swap_args=['10',0],lora=['11',0],multitalk_model=['9',0]),
      '13':node('WanVideoVAELoader',model_name='Wan2_1_VAE_bf16.safetensors',precision='bf16',use_cpu_cache=False,verbose=False),
      '14':node('WanVideoImageToVideoMultiTalk',vae=['13',0],width=832,height=480,frame_window_size=81,motion_frame=9,force_offload=True,colormatch='disabled',start_image=['1',0],tiled_vae=True,mode='infinitetalk',output_path=''),
      '15':node('WanVideoSampler',model=['12',0],image_embeds=['14',0],text_embeds=['5',0],multitalk_embeds=['7',0],steps=6,cfg=1.0,shift=11.0,seed=2026102305,force_offload=True,scheduler='dpm++_sde',riflex_freq_index=0,denoise_strength=1.0,batched_cfg=False,rope_function='comfy'),
      '16':node('WanVideoPassImagesFromSamples',samples=['15',0]),
      '19':node('ImageFromBatch',image=['16',0],batch_index=0,length=frames),
      '17':node('CreateVideo',images=['19',0],audio=['7',1],fps=25.0),
      '18':node('SaveVideo',video=['17',0],filename_prefix='dialogue_pilot',format='mp4',codec='h264'),
    }
    name=f'infinitetalk_dialogue_{frames}_exact_api.json'
    path=AI/'Workflows'/name
    encoded=json.dumps(graph,ensure_ascii=False,indent=2).encode('utf-8')
    if path.exists() and path.read_bytes()!=encoded:raise RuntimeError('Existing exact workflow differs; create a new version instead of overwriting it')
    if not path.exists():path.write_bytes(encoded)
    models={Path(x[3]).name:x[5] for x in ASSETS}
    models['umt5_xxl_fp8_e4m3fn_scaled.safetensors']=sha(AI/'Models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors')
    roles=[('firstFrame','1','LoadImage','image'),('femaleAudio','2','LoadAudio','audio'),('maleAudio','3','LoadAudio','audio')]
    return dict(id=f'infinitetalk-dialogue-{frames}-v2',version=f'infinitetalk-dialogue-{frames}-v2',fileName=name,workflowType='ImageToVideo',productionEligible=False,experimental=True,licenseStatus='LOCAL_ONLY_PENDING_REVIEW',taskTypes=['ImageToVideo'],modelFiles=list(models),modelSha256=models,nodes=[dict(role='output',nodeId='18',classType='SaveVideo',inputName='filename_prefix'),dict(role='sampler',nodeId='15',classType='WanVideoSampler',inputName='seed'),dict(role='exactFrameTrim',nodeId='19',classType='ImageFromBatch',inputName='length')],slots=[dict(role=role,nodeId=i,classType=c,inputName=field,required=True) for role,i,c,field in roles],media=dict(defaultWidth=832,defaultHeight=480,allowedDimensions=[dict(width=832,height=480)],outputFrames=[frames],nativeFps=25,allowedFps=[25],exactFrameCount=True,preserveAudio=True),notes=f'sha256={sha(path)} | exact frame trim after windowed decoding; local InfiniteTalk Multi Q8 + Wan2.1 I2V Q4_K_M; separate female-left/male-right audio and masks; requires visual review')

if __name__=='__main__':
    source=AI/'Data/Artifacts/project-32/image/task-1216/v0001/v0001_task_1216_task_1216_attempt_1_20013b81_00001__0a56bd1c7561.png'
    if sha(source)!='0a56bd1c7561197a234c04b28e95d7f04ae6789fc6fc25f77fb0fab8a23fc066':raise RuntimeError('Character reference changed')
    # Deterministic reframing of the approved identities; no new image inference.
    Image.open(source).crop((160,0,1344,684)).resize((832,480),Image.Resampling.LANCZOS).save(DATA/'pilot-reference.png')
    contract_path=ROOT/'config/workflow-contracts.json'
    backup=DATA/'workflow-contracts-before.json'
    if not backup.exists():shutil.copy2(contract_path,backup)
    doc=json.loads(contract_path.read_text(encoding='utf-8'))
    legacy=[c for c in doc['contracts'] if c['id'] in ['infinitetalk-dialogue-125-v1','infinitetalk-dialogue-241-v1']]
    if legacy:
        (DATA/'legacy-windowed-contracts.json').write_text(json.dumps(legacy,indent=2),encoding='utf-8')
        doc['contracts']=[c for c in doc['contracts'] if c not in legacy]
    for frames in [125,241]:
        contract=build(frames)
        old=next((c for c in doc['contracts'] if c['id']==contract['id']),None)
        if old is not None and old!=contract:
            if {k:v for k,v in old.items() if k!='notes'}!={k:v for k,v in contract.items() if k!='notes'}:raise RuntimeError('Existing pilot contract differs; preserved')
            old['notes']=contract['notes']
        if old is None:doc['contracts'].append(contract)
    contract_path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Two frozen experimental graphs and contracts prepared')
