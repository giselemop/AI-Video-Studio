"""V2: deterministic local inference layered over the immutable V1 controls."""
from pathlib import Path
import os,importlib.util,hashlib,random
os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
BASE=Path(__file__).with_name('acting.py');BASE_SHA='1087c1533bf092720d2e437af113213d9d3c03f8da432502e632c6fe055ac0c1'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise RuntimeError('Stable V1 controller changed')
spec=importlib.util.spec_from_file_location('stable_v1_frozen',BASE);v1=importlib.util.module_from_spec(spec);spec.loader.exec_module(v1)
v1.PROFILE='dialogue-stable-v2';original_install=v1.install;original_sink=v1.sink
def install():
    result=original_install()
    import torch,numpy as np,cv2
    # Upstream imports explicitly enable benchmark=True, so set this AFTER
    # importing its pipeline and BEFORE constructing/loading the model.
    torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1);np.random.seed(20261025);random.seed(20261025)
    cv2.setNumThreads(1);cv2.setRNGSeed(20261025)
    result.update(deterministicAlgorithms=True,cudnnBenchmark=False,tf32=False,stableV1Sha256=BASE_SHA)
    return result
def sink(path,value):
    value.update(deterministicAlgorithms=True,cudnnBenchmark=False,tf32=False,stableV1Sha256=BASE_SHA)
    original_sink(path,value)
if __name__=='__main__':
    v1.actor.verify_install=install;v1.actor._original_write=sink;v1.actor.main()
