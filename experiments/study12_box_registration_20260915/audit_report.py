"""Audit unchanged registration runs and report numeric versus physical validity."""
import hashlib,json,os,shutil,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation
import robust_box_registration as reg
from run_box_registration_pilot import read,save,sha
from report_box_registration_pilot import model,render
from run_isolated_shot_static_3d import owned_compute_job
BASE=Path(__file__).resolve().parent
PRIOR=ROOT/'EECBench/experiments/study0_box_registration_20260915/run01'

def audit(out):
    run=read(out/'run.json');inp=read(out/'box_inputs.json');fits=read(out/'fits.json');loo=read(out/'leave_one_out.json')
    a,b=np.array(inp['a']),np.array(inp['b']);L=run['baseline'];n=len(a)
    assert run['status']=='success' and len(loo)==n
    assert all(sha(p)==h for p,h in run['source_hashes'].items())
    unchanged={f:sha(ROOT/'EECBench/scripts'/f)==sha(PRIOR/'code_snapshot'/f) for f in ['robust_box_registration.py','run_box_registration_pilot.py']}
    assert all(unchanged.values())
    for fit in fits.values():
        m=model(fit['transform']);assert m[0]>0 and np.allclose(m[1].T@m[1],np.eye(3),atol=1e-10) and np.linalg.det(m[1])>.999999
        transformed=m[0]*a@m[1].T+m[2]
        direct=[min(np.sqrt(np.mean(np.sum((aa-bb[perm])**2,axis=1))) for perm in reg.PERMUTATIONS) for aa,bb in zip(transformed,b)]
        assert np.allclose(direct,fit['metrics']['per_entity_corner_rmse'],atol=1e-12)
        if 'objective_history' in fit:assert np.max(np.diff(fit['objective_history']),initial=0)<1e-10
    m=model(fits['box_huber']['transform'])
    def objective(v):
        candidate=(m[0]*np.exp(v[0]),Rotation.from_rotvec(v[1:4]).as_matrix()@m[1],m[2]+v[4:]*L)
        return float(np.mean(reg.huber(reg.box_residuals(a,b,candidate)[0]/L,.05)))
    independent=minimize(objective,np.zeros(7),method='BFGS',options={'gtol':1e-8,'maxiter':200})
    gain=objective(np.zeros(7))-float(independent.fun)
    eps=1e-6;gradient=np.array([(objective(v)-objective(-v))/(2*eps) for v in np.eye(7)*eps])
    gradient_norm=float(np.linalg.norm(gradient))
    assert gain<1e-9 and gradient_norm<1e-6,(gain,gradient_norm)
    for i,row in enumerate(loo):
        e=reg.box_residuals(a[i:i+1],b[i:i+1],model(row['transform']))[0][0]
        assert abs(e-row['heldout_corner_rmse'])<1e-10 and row['fit_excludes_tested_entity']
    idx=next(i for i,g in enumerate(inp['groups']) if g['group_id']==read(out/'synthetic_movement.json')['group_id'])
    keep=np.arange(n)!=idx
    refit=reg.fit_boxes(a[keep],b[keep],delta=.05,baseline=L,starts=4)
    assert np.max(np.abs(reg.transform(a,refit['model'])-reg.transform(a,model(loo[idx]['transform']))))<1e-10
    graph_paths=[Path(p) for p in run['source_hashes'] if Path(p).name.startswith('graph_')]
    coords=[read(p)['coordinate_system'] for p in graph_paths]
    assert all(c['z_axis']=='up' for c in coords)
    up_dot=float(m[1][2,2]);up_angle=float(np.degrees(np.arccos(np.clip(up_dot,-1,1))))
    matching=read(next(p for p in run['source_hashes'] if Path(p).name=='matching.json'))
    excluded=[g for g in matching['groups'] if g['identity']!='matched']
    result=dict(numerical_audit='pass',input_hashes_unchanged=True,solver_and_runner_identical_to_study0=unchanged,
        methods_direct_corner_replays=list(fits),proper_rotation_positive_scale=True,objective_histories_monotone=True,
        independent_BFGS_additional_cost_reduction=gain,independent_BFGS_success=bool(independent.success),
        independent_BFGS_message=str(independent.message),central_difference_gradient_norm=gradient_norm,
        loo_residual_replays=n,independent_heldout_refit=inp['groups'][idx]['group_id'],
        prior_synthetic_tests={'passed':5,'rerun_this_report':False,'evidence':str(PRIOR/'audit.json')},
        coordinate_systems=coords,up_dot_after_rotation=up_dot,up_rotation_angle_deg=up_angle,
        reverses_up_direction=up_dot<0,physical_transform_accepted=False if up_dot<0 else None,
        global_optimality_certified=False,physical_consistency_scored=False,
        excluded_group_counts=dict(Counter(g['identity'] for g in excluded)))
    save(out/'audit.json',result)
    save(out/'excluded_groups.json',excluded)
    snapshot=out/'code_snapshot';snapshot.mkdir(exist_ok=True)
    paths=[ROOT/'EECBench/scripts'/p for p in ['robust_box_registration.py','run_box_registration_pilot.py','report_box_registration_pilot.py']]+[Path(__file__).resolve()]
    provenance=[]
    for p in paths:
        dest=snapshot/p.name;shutil.copy2(p,dest);provenance.append(dict(path=str(p),sha256=sha(p),snapshot=str(dest)))
    save(out/'code_hashes.json',provenance)
    notice='该数值解会把向上方向翻转；不能作为有效物理对齐。' if up_dot<0 else '数值对齐候选；未重算一致性评分。'
    render(out,a,b,m,inp,loo,L,case_title=out.name.title(),notice=notice)
    page=(out/'alignment.html').read_text()
    assert f'<title>{out.name.title()} 数值框配准</title>' in page and f'其他{n-1}个实体' in page and notice in page
    assert read(out/'viewer_audit.json')['trace_count']==4*n
    return result

def write_case(out,check):
    run=read(out/'run.json');s=read(out/'summary.json');loo=read(out/'leave_one_out.json');sens=read(out/'sensitivity.json');L=s['baseline'];t=s['robust_transform']
    text=f'''# {out.name} Shot1 → Shot3：数值框配准

{('数值求解完成，但变换翻转向上方向，不能直接采纳为物理对齐。' if check['reverses_up_direction'] else '求得小旋转、近单位尺度的稳定数值候选；尚未执行下游一致性复核。')}

方法与 Study0 完全相同：固定匹配、3D 框和静态标签；统一 T(x)=sRx+t，八角点 RMS、24 种长方体等价编号、按实体 Huber 损失，δ=0.05。主拟合 8 个起点，留出检查 4 个起点。求解器和运行器与 Study0 快照哈希一致。

本例参与拟合 {s['matched_entities']} 组；排除组按原状态保留：{check['excluded_group_counts']}。study1 使用原 854×480 图；study2 使用原 852×480 图。没有重新提帧、缩放、检测、聚类或修改匹配。study2 对应旧 Study3（study_inconsistent_3）。

## 变换与误差

- 方向：Shot1 坐标映射到 Shot3 坐标。
- 尺度：{t['scale']:.9f}；旋转角：{t['rotation_angle_deg']:.6f}°。
- 平移：{t['translation_b']}；范数：{np.linalg.norm(t['translation_b']):.9f}。
- 长度单位为三维模型坐标单位，不是实测米；不是从视频实测的相机运动。
- L={L:.9f}，为本例目标图已匹配实体中心两两距离中位数。百分比为距离/L，越低越好，不是一致性得分。

| 方法 | 全部角点 RMSE/L | 每实体误差中位数/L |
|---|---:|---:|
'''
    for k,v in s['methods'].items():text+=f"| {k} | {100*v['normalized_corner_rmse']:.3f}% | {100*v['normalized_corner_median']:.3f}% |\n"
    text+=f'''\n留出总体 RMSE/L：{100*s['loo_corner_rmse']/L:.3f}%；留出中位数/L：{100*s['loo_normalized_corner_median']:.3f}%。留出拟合尺度范围 {s['loo_scale_range']}；相对全体拟合旋转最大变化 {s['loo_rotation_deviation_max_deg']:.3f}°，其余实体中心最大预测变化 {100*s['loo_other_prediction_shift_max']:.3f}%L。

两侧输入声明 Z 轴向上。变换后向上向量与目标向上的点积为 {check['up_dot_after_rotation']:.9f}，夹角 {check['up_rotation_angle_deg']:.3f}°。det(R)=+1 只排除镜像，不能保证保留向上方向。当前目标没有加重力方向约束。

## 逐实体检查

每次留出一个实体，仅用其余 {s['matched_entities']-1} 个实体重新拟合，随后计算该实体误差。

| 实体 | 对齐前/L | 全体拟合/L | 留出误差/L | Huber 权重 |
|---|---:|---:|---:|---:|
'''
    for r in loo:text+=f"| {r['group_id']} {r['name']} | {100*r['raw']/L:.2f}% | {100*r['fitted']/L:.2f}% | {100*r['heldout_normalized_corner_rmse']:.2f}% | {r['full_fit_weight']:.3f} |\n"
    text+='\n## 参数与复核\n\n| δ | 尺度 | 旋转角 | RMSE/L |\n|---|---:|---:|---:|\n'
    for delta in ['0.025','0.05','0.1']:
        v=sens[delta];text+=f"| {delta} | {v['transform']['scale']:.6f} | {v['transform']['rotation_angle_deg']:.3f}° | {100*v['metrics']['normalized_corner_rmse']:.3f}% |\n"
    text+=f"\n反向独立拟合后，最大角点往返误差：{100*sens['reverse_roundtrip_max_corner_error_normalized']:.3f}%L。8 个起点最终预测最大差：{s['start_solution_spread']:.3g}L；这不证明全局最优，也不保证物理正确。\n"
    if check['reverses_up_direction']:
        text+='\n本例较大残差混合了三维重建误差、可能的匹配问题及真实场景变化，不能直接全部判成视频不一致。当前解虽然降低了目标，却违反两侧共同的向上约定。后续应先加入合理的向上方向约束、检查逐实体几何；这些属于后续变体，本次主结果未更改算法或输入来修饰结果。\n'
    else:
        text+='\n书架上层书组和杯子的留出误差最大，需单独检查几何与画面。本例缺失台灯保持原未匹配状态，未进入配准，因此不能用已匹配框的低误差消除台灯缺失问题。\n'
    text+=f"\n数值与来源审计通过：4 种方法直接角点重算、{len(loo)} 项留出误差重算、独立留出重拟合、变换合法性、目标单调性及源哈希。中心差分梯度范数 {check['central_difference_gradient_norm']:.3g}；独立 BFGS 额外降低目标 {check['independent_BFGS_additional_cost_reduction']:.3g}，求解器报告 success={check['independent_BFGS_success']}（{check['independent_BFGS_message']}）。求解器沿用已通过 5 项合成测试的字节相同版本，本次没有重复这些测试。\n"
    text+='\n已有 Slurm 185272/node241 的单 CPU 执行，无 GPU、新分配或模型调用；Gs 分数未改。网页数据与标签已核对，未做浏览器交互测试。\n\n[交互式框对齐](alignment.html) · [完整变换](fits.json) · [数值及方向审计](audit.json) · [排除组原始状态](excluded_groups.json)\n'
    text+='\n输入来源：\n'+''.join(f'- `{p}`\n' for p in run['source_hashes'])
    (out/'RESULT.md').write_text(text)

if __name__=='__main__':
    owned_compute_job();assert os.getloadavg()[0]<8
    for case in ['study1','study2']:
        out=BASE/case;check=audit(out);write_case(out,check)
        print(case,json.dumps(check,ensure_ascii=False),flush=True)
