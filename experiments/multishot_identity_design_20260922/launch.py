import os,time,json,subprocess,runpy,sys
from pathlib import Path
R=Path(__file__).resolve().parent
ps=subprocess.check_output(['ps','-eo','pid,psr,pcpu,comm','--sort=-pcpu'],text=True)
def sample():
 return {int(t[0][3:]):list(map(int,t[1:])) for line in Path('/proc/stat').read_text().splitlines() if (t:=line.split())[0].startswith('cpu') and t[0][3:].isdigit()}
a=sample();time.sleep(1);b=sample();busy={int(t[1]) for line in ps.splitlines()[1:] if len(t:=line.split())>=4 and float(t[2])>10}
loads={c:1-(b[c][3]+b[c][4]-a[c][3]-a[c][4])/max(1,sum(b[c][:8])-sum(a[c][:8])) for c in os.sched_getaffinity(0)}
cores=[c for c in sorted(loads) if c<64 and loads[c]<.15 and c not in busy and c+64 not in busy and loads.get(c+64,0)<.15][:2]
assert len(cores)==2,('No safe CPUs',loads)
os.sched_setaffinity(0,cores);os.nice(10)
name=Path(sys.argv[1] if len(sys.argv)>1 else 'audit.py')
(R/('resource_'+name.stem+'.json')).write_text(json.dumps(dict(job=os.environ.get('SLURM_JOB_ID'),host=os.uname().nodename,cpus=cores,loads=loads,resident_top=ps.splitlines()[:20],gpu_hidden=True),indent=2)+'\n')
print('CPU subset',cores,flush=True);runpy.run_path(str(R/name),run_name='__main__')
