"""Bounded source checks and secret-value scan; no configured values are printed."""
from run import *
import py_compile,re
files=['server/VisualActingService.cs','server/DialogueComposeService.cs','server/GenerationQueue.DialogueComposite.cs','server/FfmpegDetailExport.cs','server/TaskSubmissionPreflightService.cs','tests/VideoStudio.QualityHarness/CaptionSinglePassRegression.cs','web/public/dialogue-stable.html','web/public/dialogue-stable.json','docs/DIALOGUE_STABLE_768_20261025.md','项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
files+=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'tools/dialogue_stable').iterdir() if p.suffix in ['.py','.ps1'])
rows=[]
for name in files:
    p=ROOT/name
    if p.suffix=='.py':
        if p.stem in sys.stdlib_module_names:raise RuntimeError('Standard-library name collision')
        py_compile.compile(str(p),doraise=True)
    rows.append(dict(path=name,sha256=sha(p),bytes=p.stat().st_size))
values=[]
for line in (ROOT/'config/local.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' not in line or line.lstrip().startswith('#'):continue
    key,value=line.split('=',1);value=value.strip().strip('"\'')
    if re.search(r'password|token|api_?key|secret',key,re.I) and len(value)>=8:values.append(value)
if any(any(v in (ROOT/name).read_text(encoding='utf-8-sig') for v in values) for name in files):raise RuntimeError('Configured secret detected; values suppressed')
result=subprocess.run(['git','diff','--check','--',*files],cwd=ROOT,capture_output=True,text=True)
if result.returncode:raise RuntimeError('Whitespace check failed')
html=(ROOT/'web/public/dialogue-stable.html').read_text(encoding='utf-8');js=FOLDER/'viewer-syntax.js';js.write_text(re.search(r'<script>(.*?)</script>',html,re.S)[1],encoding='utf-8')
subprocess.run([r'C:\Program Files\nodejs\node.exe','--check',str(js)],check=True,capture_output=True)
deployment=read(FOLDER/'deployment.json');dll=Path(deployment['executable']).with_suffix('.dll');current=ROOT/'server/bin/Release/net8.0/VideoStudio.Server.dll'
if sha(dll)!=sha(current):raise RuntimeError('Published DLL differs from current build')
write(FOLDER/'source-verification.json',dict(status='Passed',files=rows,pythonCompiled=True,standardLibraryCollisions=[],configuredSecretHits=0,diffCheckPassed=True,viewerJavaScriptParsed=True,deployedDllMatchesCurrentBuild=True,deployedDllSha256=sha(dll),branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),existingDirtyWorkPreserved=True,committed=False,pushed=False))
print('Passed: Python, JavaScript, deployed DLL, configured-secret scan, intended diff whitespace')
