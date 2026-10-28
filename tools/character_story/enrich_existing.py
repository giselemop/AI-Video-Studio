"""Add missing shoe/invariant setting fields without changing approved snapshots or media."""
from pathlib import Path
import sys,json,requests
sys.path.insert(0,str(Path(__file__).parent))
from setup import OUT,write
SHOES={19:'plain white low-top sneakers',20:'plain dark brown lace-up shoes',21:'plain white low-top canvas sneakers',22:'simple black-and-white low-top sneakers',23:'plain taupe leather loafers',24:'simple black leather lace-up shoes',25:'simple black flat walking shoes'}
def run():
    s=requests.Session();base='http://127.0.0.1:18080';a=s.get(base+'/api/auth/status').json();assert a['accessMode']=='LocalOnly' and not a['loginRequired'];s.headers['X-CSRF-Token']=a['csrfToken']
    frozen=s.get(base+'/api/character-library').json()['versions'];rows=[]
    for cid,shoes in SHOES.items():
        r=s.get(base+'/api/character-workshop/'+str(cid));r.raise_for_status();c=r.json()['character'];metadata=json.loads(c.get('metadataJson') or '{}');before=json.loads(json.dumps(metadata))
        extra=metadata.setdefault('referenceStudio',{});extra.setdefault('shoes',shoes);extra.setdefault('immutableTraits',c['fixedPrompt']);extra.setdefault('meaning','setting-and-reference-photos-not-trained-model-or-3d');extra.setdefault('contentReview','NeedReview')
        if before!=metadata:
            body=dict(c,metadata=metadata);r=s.put(base+'/api/characters/'+str(cid),json=body,timeout=60);r.raise_for_status()
        rows.append(dict(characterId=cid,beforeMetadata=before,afterMetadata=metadata,otherCharacterFieldsChanged=False,humanApproved=False))
    assert frozen==s.get(base+'/api/character-library').json()['versions']
    write(OUT/'setting-enrichment.json',dict(status='Passed',rows=rows,immutableVersionsChanged=False,newGpuTasks=0));print('Seven existing setting records gained explicit shoe and invariant fields; old versions/media unchanged.')
if __name__=='__main__':run()
