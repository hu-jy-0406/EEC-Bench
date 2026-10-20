import os,sys,json,hashlib,time,socket
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]
OLD=BASE/'experiments/study012_two_scores_20260916/study2'
RUN=HERE/'run01'
def read(p):return json.loads(Path(p).read_text())
def save(p,x):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def owned_compute_job():
 assert os.environ.get('SLURM_JOB_ID') and 'gpu' in socket.gethostname(), 'Run on checked owned compute node'
 return os.environ['SLURM_JOB_ID']
def graph(s):return read(RUN/'camera_inputs'/f'{s}.json')
def no_identity_audit(event,args):
 if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
  name=Path(os.fsdecode(args[0])).name
  if name in {'matching.json','aligned_entities.json','all_pair_cosines.json','spatial.json','presence.json'}:raise RuntimeError('Identity-free registration cannot open '+name)
sys.addaudithook(no_identity_audit)
