"""Verify crash-safe submissions without creating any service task."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import run


def main():
    checks=[]
    with TemporaryDirectory(dir=run.FOLDER,prefix='guard-') as folder:
        original=run.FOLDER
        run.FOLDER=Path(folder)
        try:
            calls=[]
            def unexpected(*args,**kwargs):
                calls.append((args,kwargs))
                raise AssertionError('No API request was expected')
            state={'jobSubmissionStarted':True}
            fake=SimpleNamespace(state=state,api=unexpected,save=unexpected,poll=unexpected)
            try:
                run.once(fake,'job','Pending','/api/tasks',{'x':1})
                raise AssertionError('Unresolved submission was not rejected')
            except RuntimeError as error:
                assert 'unresolved' in str(error)
            assert not calls
            checks.append('Unresolved submission cannot create a duplicate task')
            state={'job':12,'jobInput':{'x':1}}
            fake.state=state
            try:
                run.once(fake,'job','Pending','/api/tasks',{'x':2})
                raise AssertionError('Changed frozen input was not rejected')
            except RuntimeError as error:
                assert 'changed' in str(error)
            assert not calls
            checks.append('Changed frozen inputs cannot reuse an existing task identity')
            detail={'task':{'id':12,'status':'Succeeded'},'results':[]}
            fake.poll=lambda task_id: detail if task_id==12 else None
            assert run.once(fake,'job','Pending','/api/tasks',{'x':1})==detail
            assert not calls
            checks.append('An existing successful task is queried without another POST')
            fake.state={'shot1TaskId':1230}
            try:
                run.frame(fake,1)
                raise AssertionError('A frozen opening was not protected')
            except RuntimeError as error:
                assert 'already frozen' in str(error)
            assert not calls
            checks.append('An existing video prevents accidental opening-frame generation or reselection')
            starts=[line[0] for line in run.LINES]
            assert starts==sorted(starts) and len(run.SHOTS)==6 and starts[-1]<31
            assert len({shot['number'] for shot in run.SHOTS})==6
            checks.append('Six distinct story beats and ordered dialogue timing fit the declared duration')
        finally:
            run.FOLDER=original
    report={'status':'Passed','checks':checks,'newTaskSubmitted':False}
    (run.FOLDER/'guard-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
