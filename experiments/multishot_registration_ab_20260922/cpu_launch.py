import os,time,json,subprocess,runpy,sys
from pathlib import Path
R=Path(__file__).resolve().parent
ps=subprocess.check_output(['ps','-eo','pid,psr,pcpu,rss,comm','--sort=-pcpu'],text=True)
def sample():
 return {int(t[0][3:]):list(map(int,t[1:])) for l in Path('/proc/stat').read_text().splitlines() if (t:=l.split())[0].startswith('cpu') and t[0][3:].isdigit()}
a=sample();time.sleep(1);b=sample();busy={int(t[1]) for l in ps.splitlines()[1:] if len(t:=l.split())>=4 and float(t[2])>10};allowed=os.sched_getaffinity(0)
loads={c:1-(b[c][3]+b[c][4]-a[c][3]-a[c][4])/max(1,sum(b[c][:8])-sum(a[c][:8])) for c in allowed}
cores=[c for c in sorted(loads) if c<64 and loads[c]<.15 and c not in busy and c+64 not in busy and loads.get(c+64,0)<.15][:4]
assert len(cores)==4,('No safe CPU subset',loads);os.sched_setaffinity(0,cores);os.nice(10)
(R/('resource_'+Path(sys.argv[1]).stem+'_'+str(os.getpid())+'.json')).write_text(json.dumps(dict(job=os.environ.get('SLURM_JOB_ID'),host=os.uname().nodename,cpus=cores,loads=loads,resident_top=ps.splitlines()[:20]),indent=2))
script=Path(sys.argv[1]);sys.argv=sys.argv[1:];print('CPU subset',cores,flush=True);runpy.run_path(str(script),run_name='__main__')
