"""Paired warm CPU benchmark: FPS overhead versus optimizer savings."""
import hashlib,json,os,platform,random,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[2];ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'scripts'))
import numpy as np
from gs_registration_3d import fit_all_pairs
from gs_registration_variants import select_pairs
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job()
OUT=ROOT/'fps_timing';OUT.mkdir(exist_ok=False)
def cpu_snapshot():
 return {int(l.split()[0][3:]):list(map(int,l.split()[1:9])) for l in Path('/proc/stat').read_text().splitlines() if l.startswith('cpu') and l.split()[0]!='cpu'}
a=cpu_snapshot();time.sleep(1);b=cpu_snapshot();util={}
for c in set(range(0,32))|set(range(64,96)):
 if c in os.sched_getaffinity(0):
  delta=np.array(b[c])-a[c];util[c]=1-float(delta[3]+delta[4])/max(1,int(delta.sum()))
core=min(util,key=lambda c:(util[c],c));assert util[core]<.10,util
os.sched_setaffinity(0,{core})
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,d:p.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
paths={'study2':BASE/'experiments/study2_integrated_full_fresh_20260919/study2/registration/roma_geometry/correspondences.npz','study3':BASE/'experiments/study3/run_cpu02/registration/roma_geometry/correspondences.npz'}
data={k:np.load(p)['data'] for k,p in paths.items()};hashes={str(p):sha(p) for p in [*paths.values(),BASE/'scripts/gs_registration_3d.py',BASE/'scripts/gs_registration_variants.py',Path(__file__)]}
for name,d in data.items():
 for k in [32,64,128]:assert select_pairs(d,k,'fps',.2).tolist()==read(ROOT/name/f'm1_fps_{k}/registration.json')['selected_rows']
def run(name,k):
 d=data[name];t0=time.perf_counter();c0=time.process_time()
 ix=np.arange(len(d)) if k==0 else select_pairs(d,k,'fps',.2)
 t1=time.perf_counter();c1=time.process_time()
 fit=fit_all_pairs(d[ix,7:10],d[ix,10:13],yaw_starts=24,extra_starts=())
 t2=time.perf_counter();c2=time.process_time()
 assert len(fit['attempts'])==25
 expected=read(ROOT/name/f'm1_fps_{k}/registration.json')['fit']['objective_value'] if k else read(BASE/'experiments/registration_3d_sum_20260919'/name/'registration.json')['fits']['all_structures']['objective_value']
 assert abs(fit['objective_value']-expected)<1e-7
 return dict(case=name,k=k,pairs=len(ix),selection_ms=1000*(t1-t0) if k else 0.,solve_ms=1000*(t2-t1),total_ms=1000*(t2-t0),selection_cpu_ms=1000*(c1-c0) if k else 0.,solve_cpu_ms=1000*(c2-c1),total_cpu_ms=1000*(c2-c0),objective=fit['objective_value'],total_solver_evaluations=sum(a['evaluations'] for a in fit['attempts']))
jobs=[(name,k) for name in data for k in [0,32,64,128]]
for name,k in jobs:run(name,k)
raw=[];rng=random.Random(20260919)
for rep in range(10):
 order=jobs.copy();rng.shuffle(order)
 for name,k in order:raw.append(dict(repeat=rep,**run(name,k)))
 print('completed repeat',rep+1,flush=True)
summary=[]
for name,k in jobs:
 r=[r for r in raw if r['case']==name and r['k']==k];stats={key:dict(median=float(np.median([x[key] for x in r])),p10=float(np.quantile([x[key] for x in r],.1)),p90=float(np.quantile([x[key] for x in r],.9))) for key in ['selection_ms','solve_ms','total_ms','selection_cpu_ms','solve_cpu_ms','total_cpu_ms']}
 paired=[]
 for x in r:
  base=next(v for v in raw if v['case']==name and v['k']==0 and v['repeat']==x['repeat'])
  paired.append(dict(solve_saved_ms=base['solve_ms']-x['solve_ms'],net_saved_ms=base['total_ms']-x['total_ms']))
 summary.append(dict(case=name,k=k,pairs=r[0]['pairs'],**stats,paired_median_solve_saved_ms=float(np.median([x['solve_saved_ms'] for x in paired])),paired_median_net_saved_ms=float(np.median([x['net_saved_ms'] for x in paired]))))
for p,h in hashes.items():assert sha(Path(p))==h
save(OUT/'raw.json',raw);save(OUT/'summary.json',summary);save(OUT/'audit.json',dict(passed=True,same_25_start_policy=True,selected_rows_match_previous=True,objectives_match_previous=True,input_hashes_unchanged=True,hashes=hashes,new_model_tokens=0))
save(OUT/'protocol.json',dict(host=platform.node(),job=os.environ.get('SLURM_JOB_ID'),cpu_core=core,cpu_busy_fraction_at_start=util[core],threads=1,nice=os.getpriority(os.PRIO_PROCESS,0),warmup_each_variant=1,repetitions=10,execution_order='seeded shuffled variants within each repeat',timing='warm in-memory function calls, perf_counter and process_time; excludes loading/imports/RoMA/lifting/API/I/O',solver='same code/settings: 24 yaw grid starts + one data-derived initializer; no historical extra start',sampling='existing joint endpoint 6D FPS; confidence floor 0.2 unchanged'))
lines=['# FPS采样与优化求解分项计时','','同一节点单CPU线程、固定核、每种设置预热1次，再交错随机顺序重复10次。两种点数规模采用相同优化器和25初值策略；未使用历史额外初值。下表为各分项耗时中位数，单位毫秒；不含RoMA、读盘、导入、lift、API和输出。配对节省为每轮差值的中位数，因此不必严格等于表中中位数之差。','','|测例|点对数|FPS采样|优化求解|合计|求解节省|扣除FPS后净节省|','|---|---:|---:|---:|---:|---:|---:|']
for r in summary:
 lines.append(f"|{r['case']}|{r['pairs']}|{r['selection_ms']['median']:.2f}|{r['solve_ms']['median']:.2f}|{r['total_ms']['median']:.2f}|{r['paired_median_solve_saved_ms']:.2f}|{r['paired_median_net_saved_ms']:.2f}|")
lines+=['','FPS计时包含候选筛选、归一化和最远点选择。优化计时包含选中坐标提取、初始化、所有多初值求解与结果构造。结果复现此前选中行和目标值；所有输入哈希未改。raw.json保存全部wall/CPU计时，summary.json包含p10/p90。','','本次只测CPU数值阶段。历史RoMA为Study2 GPU132.559秒、Study3 CPU2732.829秒；FPS不改变此成本，不能把数值阶段加速比当成整条pipeline加速比。']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True)
