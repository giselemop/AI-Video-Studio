"""Second targeted attempt only, following explicit recorded visual rejection."""
from run import Repair

if __name__=='__main__':
 r=Repair()
 for cid,view in [(21,'threeQuarterLeft'),(21,'threeQuarterRight'),(22,'threeQuarterRight'),(23,'threeQuarterRight'),(25,'threeQuarterLeft')]:
    r.inspect(f'{cid}-{view}-fullBody-a1','Failed','Inspected full-resolution centre crop: the torso is frontal instead of the requested front-quarter orientation. Head/limbs mostly normal, but direction fails. Retain original output; do not collect as the requested slot.')
    r.submit(cid,view,'fullBody',2,'Use the existing matching front-quarter FACE reference as the sole image input; retain that same identity and 35-degree direction. Generate the full body with head, shoulders, chest, pelvis and feet all following the same gentle diagonal. Preserve specified clothing and shoes from text. Do not return to a frontal torso. Closed lips and neutral expression. One head and anatomically coherent arms and legs.')
