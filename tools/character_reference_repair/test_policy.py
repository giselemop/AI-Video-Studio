"""Cross-runtime prompt parity, crop conflicts and original checkpoint immutability."""
import importlib.util, sys
from inventory import ROOT, DATA, OUT, read, write, sha
sys.path.insert(0,str(ROOT/'tools'))
from character_prompt_policy import compose, POLICY, SLOTS

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run():
 checks=[]
 def check(value,name):
    checks.append(dict(name=name,status='Passed' if value else 'Failed'))
    if not value:raise AssertionError(name)
 for row in read(OUT/'prompt-matrix-dotnet.json'):
    actual=compose(row['view'],row['framing'],row['count'],'oval face, adult age 30','green cotton top, black trousers, white shoes','natural adult proportions')
    check(actual==row['prompt'],f"Python/.NET parity {row['view']} {row['framing']} {row['count']}")
 for case in [('bad','fullBody',1),('back','closeUp',1),('front','closeUp',3)]:
    rejected=False
    try:compose(*case)
    except ValueError:rejected=True
    check(rejected,'invalid combination '+str(case))
 p=compose('right','fullBody',2,'existing adult face','green top','natural proportions')
 check('far eye and far side of the face are occluded' in p and 'both eyes remain naturally visible' not in p,'profile hides far eye')
 check('no second face' in p and 'normal scalp and hairstyle' in p,'rear head cannot gain a second face')
 check('do not copy its head, face, pose or camera angle' in p,'wardrobe image cannot define another head')
 check('occlusion are allowed' in p and 'BOTH hands' not in p,'far limbs not forced into visibility')
 check('black trousers' not in compose('front','closeUp',1,'adult face','green top、black trousers、white shoes'),'Chinese wardrobe separated from close-up')
 checkpoints={}
 for name,filename in [('referencepack','character_reference_pack/run.py'),('expansion','character_expansion/batch.py')]:
    module=load('test_'+name,ROOT/'tools'/filename);folder=module.FOLDER
    before=sha(folder/'run.json');state=read(folder/'run.json');runner=module.Run() if name=='referencepack' else module.Batch()
    for person in module.PEOPLE:
        for view,framing in module.SLOTS:
            key=person['key']+'-'+view+'-'+framing
            if key not in state['tasks'] or not state['tasks'][key].get('body'):continue
            actual=runner.head_body(person) if name=='expansion' and (view,framing)==('front','closeUp') else runner.image_body(person,view,framing)
            check(actual==state['tasks'][key]['body'],'frozen historical request preserved '+key)
    check(before==sha(folder/'run.json'),name+' checkpoint not rewritten')
    checkpoints[str(folder/'run.json')]=before
 write(OUT/'prompt-tests.json',dict(status='Passed',checks=checks,policy=POLICY['version'],newGpuTasks=0,checkpoints=checkpoints))
 print('PROMPT_TESTS_PASSED',len(checks),'checks; no GPU task submitted')
if __name__=='__main__':run()
