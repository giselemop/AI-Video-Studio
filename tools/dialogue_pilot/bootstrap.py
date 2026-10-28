"""Pinned public model downloads; no inference or cloud API calls."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'minimax'))
from download_assets import download as ranged_download, download_lock

AI = Path(r'C:\install\AI')
OUT = AI/'Data/DialoguePilot20261023'
OUT.mkdir(parents=True, exist_ok=True)
ASSETS = [
 ('city96/Wan2.1-I2V-14B-480P-gguf', 'b4b6b3b3f0f64975fb33b1d5d1a46ca24e065f03', 'wan2.1-i2v-14b-480p-Q4_K_M.gguf', 'diffusion_models/wan2.1-i2v-14b-480p-Q4_K_M.gguf', 11341184384, 'd91f7139acadb42ea05cdf97b311e5099f714f11fbe4d90916500e2f53cbba82'),
 ('Kijai/WanVideo_comfy_GGUF', '8418a4ed00314a49f44b73a0d43d40aa539264da', 'InfiniteTalk/Wan2_1-InfiniteTalk_Multi_Q8.gguf', 'diffusion_models/Wan2_1-InfiniteTalk_Multi_Q8.gguf', 2646330016, '2b9b1dc2fb0f0a351e688ad8dc7545bf90b2a2f20cd91953ac077510ef6b7bc0'),
 ('Kijai/WanVideo_comfy', '8260d429d19fd7a72304cad059160b95d843913f', 'Wan2_1_VAE_bf16.safetensors', 'vae/Wan2_1_VAE_bf16.safetensors', 253806278, '1ab9a32cc2c740f6e39d80d367ce5dcc28db8c71b79b28670546b8973e9d75f9'),
 ('Kijai/WanVideo_comfy', '8260d429d19fd7a72304cad059160b95d843913f', 'Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors', 'loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors', 738005744, '85c4a61c30e0497aa44b91d93a893b624708461a56fe5485183b28fa07e2dfb3'),
 ('Kijai/wav2vec2_safetensors', '87847d3bc53702afda44078249e7c33e867827c4', 'wav2vec2-chinese-base_fp16.safetensors', 'wav2vec2/wav2vec2-chinese-base_fp16.safetensors', 190115368, '000813e441020f18cff844c969d2d5d4adc2a5ce46b2db1f23950b05d88805b4'),
]

def download(item):
    repo, rev, source, dest, size, expected = item
    path = AI/'Models'/dest
    path.parent.mkdir(parents=True, exist_ok=True)
    ranged_download(dict(repository=repo,revision=rev,file=source,target=dest,size=size,sha256=expected),AI/'Models',16,32*1024*1024)
    return dict(path=str(path),sha256=expected,bytes=size,repo=repo,revision=rev,source=source)

if __name__ == '__main__':
    (OUT/'model-manifest.json').write_text(json.dumps(ASSETS,indent=2),encoding='utf-8')
    with download_lock(OUT,filename='.pilot-assets.lock'):
        result = [download(item) for item in ASSETS]
    (OUT/'model-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('All five assets verified',flush=True)
