"""Add the shared policy pointer; fill only missing proportions from existing frozen data."""
import json
from run import Repair
from inventory import OUT, write

if __name__=='__main__':
 r=Repair();rows=[]
 for cid in range(19,26):
    c=r.api('/api/character-workshop/'+str(cid))['character'];metadata=json.loads(c.get('metadataJson') or '{}')
    before=dict(metadata=json.loads(json.dumps(metadata)),bodyRatio=c.get('bodyRatio'))
    studio=metadata.setdefault('referenceStudio',{});studio['promptPolicy']='character-anatomy-v2'
    if not c.get('bodyRatio') and cid in (19,20):
        version=next(v['payload'] for v in r.before['versions'] if v['id']==(4 if cid==19 else 5));c['bodyRatio']=version['bodyRatio']
    r.api('/api/characters/'+str(cid),dict(c,metadata=metadata),method='PUT')
    rows.append(dict(characterId=cid,before=before,after=dict(metadata=metadata,bodyRatio=c.get('bodyRatio')),source='existing character settings and frozen body description; no new face trait invented'))
 write(OUT/'setting-policy-enrichment.json',dict(rows=rows,approvedReferencesChanged=False,immutableVersionsChanged=False))
