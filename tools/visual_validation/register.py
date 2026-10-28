"""Register an additive, hash-pinned Klein workflow. Never submits GPU tasks."""
from run import ROOT, DATA, FOLDER, Run, read, write, sha
import shutil

setup=ROOT/'tools/visual_pilot_keyframes'
template=setup/'flux2_klein4b_keyframe_api.json'
definition=read(setup/'contract-definition.json')
target=ROOT.parent/'Workflows'/definition['fileName']
if target.exists() and sha(target)!=sha(template):raise RuntimeError('Existing template differs; version instead of overwriting')
if not target.exists():shutil.copy2(template,target)
path=ROOT/'config/workflow-contracts.json'
doc=read(path);old=[c for c in doc['contracts'] if c['id']==definition['id']]
if old and old!=[definition]:raise RuntimeError('Existing contract differs')
if not old:doc['contracts'].append(definition);write(path,doc)
model_paths=ROOT.parent/'ComfyUI/extra_model_paths.yaml'
before=model_paths.read_text(encoding='utf-8-sig')
marker='visual_pilot_klein:'
addition='\nvisual_pilot_klein:\n  base_path: C:/install/AI/Models/Flux2Klein4B/\n  diffusion_models: diffusion_models/\n  text_encoders: text_encoders/\n  vae: vae/\n'
if marker not in before:
    backup=FOLDER/'backups/root/extra_model_paths.yaml';backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(model_paths,backup)
    model_paths.write_text(before.rstrip()+'\n'+addition,encoding='utf-8')
write(FOLDER/'keyframe-registration.json',dict(status='RegisteredOnly',workflow=str(target),sha256=sha(target),contract=definition['id'],gpuTasksSubmitted=0))
print('Additive Klein workflow and model search path registered; restart idle ComfyUI before loading new paths')
