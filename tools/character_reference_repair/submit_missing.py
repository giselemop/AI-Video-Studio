"""Known missing front-quarter slots, each submitted at most once."""
from run import Repair

if __name__=='__main__':
 r=Repair()
 for cid,view in [(21,'threeQuarterLeft'),(21,'threeQuarterRight'),(22,'threeQuarterRight'),(23,'threeQuarterRight'),(25,'threeQuarterLeft'),(20,'threeQuarterLeft')]:
    r.submit(cid,view,'fullBody',1,'Correct the missing or overly side-on front-quarter slot. Rotate the whole person only 35 degrees toward picture '+('LEFT' if view.endswith('Left') else 'RIGHT')+'. Show both eyes naturally and the broad front of the chest, with a coherent single head, normal relaxed arms, two connected legs and complete shoes. Preserve identity, age and outfit.')
