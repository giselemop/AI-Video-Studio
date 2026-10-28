"""Record only this change's sources, deployed build and local checks."""
from run import *
import re,py_compile

files=[
    'server/VisualActingService.cs','server/GenerationQueue.VisualActing.cs',
    'server/GenerationQueue.cs','server/DialogueComposeService.cs',
    'server/GenerationQueue.DialogueComposite.cs','server/TaskSubmissionPreflightService.cs',
    'server/FfmpegDetailExport.cs','server/GenerationQueue.VideoDetail.cs',
    'tests/VideoStudio.QualityHarness/CaptionSinglePassRegression.cs',
    'tests/VideoStudio.QualityHarness/Program.cs',
    'web/public/dialogue-visual.html','web/public/dialogue-visual.json',
    'docs/DIALOGUE_VISUAL_20261025.md',
    '项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md',
    'CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md',
]
files+=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'tools/dialogue_visual').iterdir() if p.suffix in ['.py','.ps1'])
files=sorted(set(files));rows=[]
for name in files:
    p=ROOT/name
    if not p.is_file():raise RuntimeError('Missing intended source: '+name)
    if p.suffix=='.py':py_compile.compile(str(p),doraise=True)
    rows.append(dict(path=name,sha256=sha(p),bytes=p.stat().st_size))
secret_values=[]
env=ROOT/'config/local.env'
if env.exists():
    for line in env.read_text(encoding='utf-8-sig').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);value=value.strip().strip('\"\'')
        if re.search(r'password|token|api_?key|secret',key,re.I) and len(value)>=8:
            secret_values.append(value)
hits=[name for name in files if any(v in (ROOT/name).read_text(encoding='utf-8-sig') for v in secret_values)]
if hits:raise RuntimeError('Configured secret found in intended source files: '+','.join(hits))
diff=subprocess.run(['git','diff','--check','--',*files],cwd=ROOT,capture_output=True,text=True)
if diff.returncode:raise RuntimeError('Intended-source whitespace check failed: '+diff.stdout+diff.stderr)
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
media_tracked=[p for p in tracked if re.search(r'\.(mp4|mov|wav|mp3|safetensors|gguf|ckpt|pth|onnx)$',p,re.I)]
if media_tracked:raise RuntimeError('Review tracked generated media/model files: '+','.join(media_tracked))
deployment=read(FOLDER/'deployment.json');exe=Path(deployment['executable']);dll=exe.with_suffix('.dll')
if 'DialogueVisual20261025V2' not in str(exe):raise RuntimeError('Unexpected final deployment')
reports=[]
for name in ['acceptance/visual_acting_0a803014e9ef4b51a61648443d6b2f3d/report.json',
             'acceptance/caption_singlepass_18f7cf82462e4b6792411c2600b671ca/report.json',
             'DialogueVisual20261025/api-admission-checks.json','DialogueVisual20261025/caption-api-checks.json',
             'DialogueVisual20261025/viewer-syntax-check.json','DialogueVisual20261025/completed-guard-checks.json']:
    p=DATA/name;report=read(p)
    if report['status']!='Passed':raise RuntimeError('Referenced check has not passed: '+name)
    reports.append(dict(path=name,sha256=sha(p),status='Passed',checks=len(report.get('checks',[]))))
write(FOLDER/'source-manifest.json',dict(status='Passed',files=rows,pythonCompile='Passed',
    intendedSourceDiffCheck='Passed',configuredSecretScan='Passed',secretValuesDisclosed=False,
    trackedGeneratedVideosOrModelWeights=[],deployment=deployment,
    deployedExecutableSha256=sha(exe),deployedDllSha256=sha(dll),
    testReports=reports,
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    scope='Only this change; unrelated dirty work preserved; no commit or push'))
print('Passed: intended-source hashes, Python compile, whitespace, configured-secret scan and deployed V2 build recorded')
