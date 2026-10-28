"""Hash the intended additive change and actual acceptance reports, not unrelated work."""
from run import *
import py_compile,re
files=['server/GenerationQueue.cs','tests/VideoStudio.QualityHarness/H3Regression.cs','server/VisualActingService.cs','server/DialogueComposeService.cs','server/GenerationQueue.DialogueComposite.cs','config/workflow-contracts.json',
       'web/public/dialogue-sync-full.html','web/public/dialogue-sync-full.json','docs/DIALOGUE_SYNC_FULL_20261025.md',
       '项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
files+=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'tools/dialogue_sync_full').iterdir() if p.suffix in ['.py','.ps1'])
rows=[]
collisions=[p.name for p in (ROOT/'tools/dialogue_sync_full').glob('*.py') if p.stem in sys.stdlib_module_names]
if collisions:raise RuntimeError('Pilot helper shadows Python standard library: '+','.join(collisions))
for name in files:
    p=ROOT/name
    if p.suffix=='.py':py_compile.compile(str(p),doraise=True)
    rows.append(dict(path=name,sha256=sha(p),bytes=p.stat().st_size))
secret_values=[]
for line in (ROOT/'config/local.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' not in line or line.lstrip().startswith('#'):continue
    key,value=line.split('=',1);value=value.strip().strip('\"\'')
    if re.search(r'password|token|api_?key|secret',key,re.I) and len(value)>=8:secret_values.append(value)
hits=[name for name in files if any(v in (ROOT/name).read_text(encoding='utf-8-sig') for v in secret_values)]
if hits:raise RuntimeError('Configured secret found in intended files: '+','.join(hits))
diff=subprocess.run(['git','diff','--check','--',*files],cwd=ROOT,capture_output=True,text=True)
if diff.returncode:raise RuntimeError('Intended-source whitespace check failed: '+diff.stdout+diff.stderr)
html=(ROOT/'web/public/dialogue-sync-full.html').read_text(encoding='utf-8');js=FOLDER/'viewer-syntax.js';js.write_text(re.search(r'<script>(.*?)</script>',html,re.S)[1],encoding='utf-8')
node=subprocess.run([r'C:\Program Files\nodejs\node.exe','--check',str(js)],capture_output=True,text=True)
if node.returncode:raise RuntimeError(node.stderr)
deployment=read(FOLDER/'deployment.json');exe=Path(deployment['executable'])
if 'DialogueSyncFull20261025V2' not in str(exe):raise RuntimeError('Unexpected deployment')
reports=[]
for name in ['prepared-inputs.json','voice-window-checks.json','driver-recovery.json','deadline-regression.json','caption-render-checks.json','legacy-protocol-checks.json','api-admission-checks.json','composition-admission-checks.json','final-verification.json','preview-publication.json','browser-playback.json','final-environment-verification.json','completed-guard-checks.json']:
    p=FOLDER/name
    if read(p)['status']!='Passed':raise RuntimeError('Acceptance report incomplete: '+name)
    reports.append(dict(path=rel(p),sha256=sha(p),status='Passed'))
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
bad=[p for p in tracked if re.search(r'\.(mp4|mov|wav|mp3|safetensors|gguf|ckpt|pth|onnx)$',p,re.I)]
if bad:raise RuntimeError('Tracked generated media/model weights require review')
built=ROOT/'server/bin/Release/net8.0/VideoStudio.Server.dll'
if sha(built)!=sha(exe.with_suffix('.dll')):raise RuntimeError('Deployed service DLL differs from current validated build')
write(FOLDER/'source-manifest.json',dict(status='Passed',files=rows,reports=reports,pythonCompile='Passed',stdlibShadowingCheck='Passed',viewerJavaScriptSyntax='Passed',configuredSecretScan='Passed',
    secretValuesDisclosed=False,intendedDiffCheck='Passed',trackedGeneratedMediaOrWeights=[],deployment=deployment,deployedExeSha256=sha(exe),deployedDllSha256=sha(exe.with_suffix('.dll')),
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    deployedMatchesValidatedBuild=True,scope='Only this additive change; unrelated dirty work preserved; no commit/push'))
print('Passed: intended sources, Python/JS checks, configured-secret scan, deployed build and actual reports recorded')
