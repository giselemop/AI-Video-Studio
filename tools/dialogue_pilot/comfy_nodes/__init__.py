"""Deterministic speaker-region assignment for a static, two-person pilot."""
import torch
import gc
import hashlib
import json
from pathlib import Path

class DialogueSpeakerMasks:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'image':('IMAGE',),'split_ratio':('FLOAT',{'default':.395,'min':.1,'max':.9,'step':.001})}}
    RETURN_TYPES=('MASK',)
    FUNCTION='make'
    CATEGORY='VideoStudio/Dialogue'
    def make(self,image,split_ratio):
        height,width=image.shape[1:3]
        boundary=round(width*split_ratio)
        masks=torch.zeros((2,height,width),dtype=torch.float32,device='cpu')
        masks[0,:,:boundary]=1
        masks[1,:,boundary:]=1
        return (masks,)

class NativeWanTextCached:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        return {'required':{'model_name':(folder_paths.get_filename_list('text_encoders'),),'positive':('STRING',{'multiline':True}),'negative':('STRING',{'multiline':True})}}
    RETURN_TYPES=('WANVIDEOTEXTEMBEDS',)
    FUNCTION='encode'
    CATEGORY='VideoStudio/Dialogue'
    def encode(self,model_name,positive,negative):
        import folder_paths
        import nodes
        import comfy.model_management as mm
        from safetensors.torch import load_file,save_file
        model=Path(folder_paths.get_full_path_or_raise('text_encoders',model_name))
        identity=dict(model=str(model),size=model.stat().st_size,mtime=model.stat().st_mtime_ns,positive=positive,negative=negative,route='comfy-native-wan-v1')
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        cache=Path(r'C:\install\AI\Data\DialoguePilot20261023\text-cache')
        cache.mkdir(parents=True,exist_ok=True)
        target=cache/(key+'.safetensors')
        if target.exists():
            embeddings=load_file(target)
        else:
            clip,=nodes.CLIPLoader().load_clip(model_name,'wan',device='default')
            embeddings={}
            for label,text in [('prompt_embeds',positive),('negative_prompt_embeds',negative)]:
                encoded=clip.encode_from_tokens_scheduled(clip.tokenize(text))
                embeddings[label]=encoded[0][0].detach().cpu().contiguous()
            mm.unload_all_models()
            del encoded,clip
            gc.collect()
            mm.soft_empty_cache()
            save_file(embeddings,str(target))
            (cache/(key+'.json')).write_text(json.dumps(identity,indent=2),encoding='utf-8')
        return (embeddings,)

class AudioModelAfterText:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'model':('MULTITALKMODEL',),'text':('WANVIDEOTEXTEMBEDS',)}}
    RETURN_TYPES=('MULTITALKMODEL',)
    FUNCTION='after'
    CATEGORY='VideoStudio/Dialogue'
    def after(self,model,text):return (model,)

NODE_CLASS_MAPPINGS={'VideoStudioDialogueSpeakerMasks':DialogueSpeakerMasks,'VideoStudioNativeWanTextCached':NativeWanTextCached,'VideoStudioAudioModelAfterText':AudioModelAfterText}
NODE_DISPLAY_NAME_MAPPINGS={'VideoStudioDialogueSpeakerMasks':'VideoStudio: female left / male right masks'}
