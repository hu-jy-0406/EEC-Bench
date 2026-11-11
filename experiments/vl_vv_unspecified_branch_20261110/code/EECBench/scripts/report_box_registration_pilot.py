"""Independent arithmetic checks and an offline before/after registration view."""
import argparse,hashlib,html,itertools,json,shutil,sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation
import robust_box_registration as reg
from run_isolated_shot_static_3d import owned_compute_job

ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def model(d):return d['scale'],np.array(d['R_b_from_a']),np.array(d['translation_b'])
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

def main(out):
    owned_compute_job()
    run=read(out/'run.json');assert run['status']=='success'
    for p,h in run['source_hashes'].items():assert sha(Path(p))==h
    inp=read(out/'box_inputs.json');a,b=np.array(inp['a']),np.array(inp['b']);baseline=run['baseline']
    fits=read(out/'fits.json');checks=[]
    for name,fit in fits.items():
        m=model(fit['transform']);assert m[0]>0 and np.allclose(m[1].T@m[1],np.eye(3),atol=1e-10) and np.linalg.det(m[1])>.999999
        # Direct full enumeration, distinct from the vectorized fitting residual.
        transformed=m[0]*a@m[1].T+m[2]
        errors=[min(np.sqrt(np.mean(np.sum((aa-bb[perm])**2,axis=1))) for perm in reg.PERMUTATIONS) for aa,bb in zip(transformed,b)]
        assert np.allclose(errors,fit['metrics']['per_entity_corner_rmse'],atol=1e-12)
        if 'objective_history' in fit:assert np.max(np.diff(fit['objective_history']),initial=0)<1e-10
        checks.append(name)
    m=model(fits['box_huber']['transform'])
    # Check stationarity using a different optimizer and local seven-parameter
    # coordinates. This checks the reported local optimum, not global optimality.
    def objective(v):
        candidate=(m[0]*np.exp(v[0]),Rotation.from_rotvec(v[1:4]).as_matrix()@m[1],m[2]+v[4:]*baseline)
        e=reg.box_residuals(a,b,candidate)[0]/baseline
        return float(np.mean(reg.huber(e,.05)))
    independent=minimize(objective,np.zeros(7),method='BFGS',options=dict(gtol=1e-8,maxiter=200))
    gain=objective(np.zeros(7))-float(independent.fun)
    eps=1e-6
    basis=np.eye(7)*eps
    gradient=np.array([(objective(v)-objective(-v))/(2*eps) for v in basis])
    gradient_norm=float(np.linalg.norm(gradient))
    assert gain<1e-9 and gradient_norm<1e-6
    loo=read(out/'leave_one_out.json')
    for i,row in enumerate(loo):
        e=reg.box_residuals(a[i:i+1],b[i:i+1],model(row['transform']))[0][0]
        assert abs(e-row['heldout_corner_rmse'])<1e-10 and row['fit_excludes_tested_entity']
    # Refit one held-out item from its independently reconstructed 15-box subset.
    idx=next(i for i,g in enumerate(inp['groups']) if g['group_id']=='g07')
    keep=np.arange(len(a))!=idx
    refit=reg.fit_boxes(a[keep],b[keep],delta=.05,baseline=baseline,starts=4)
    assert np.max(np.abs(reg.transform(a,refit['model'])-reg.transform(a,model(loo[idx]['transform']))))<1e-10
    audit=dict(status='pass',source_hashes_unchanged=True,methods_direct_corner_replays=checks,
               positive_scale_proper_rotation_all=True,objective_histories_monotone=True,
               independent_BFGS_additional_cost_reduction=gain,independent_BFGS_success=bool(independent.success),
               independent_BFGS_message=str(independent.message),
               central_difference_gradient_norm=gradient_norm,
               loo_residual_replays=16,independent_heldout_refit='g07',tests_passed=5,
               global_optimality_certified=False,physical_consistency_scored=False)
    save(out/'audit.json',audit)
    # Freeze the small new code closure. Existing graph/release files are untouched.
    snapshot=out/'code_snapshot';snapshot.mkdir(exist_ok=True)
    paths=[ROOT/'EECBench/scripts'/n for n in ['robust_box_registration.py','run_box_registration_pilot.py','report_box_registration_pilot.py']]+[ROOT/'EECBench/tests/test_robust_box_registration.py']
    provenance=[]
    for p in paths:
        dest=snapshot/p.name;shutil.copy2(p,dest);provenance.append(dict(path=str(p),sha256=sha(p),snapshot=str(dest)))
    save(out/'code_hashes.json',provenance)
    summary=read(out/'summary.json');stress=read(out/'synthetic_movement.json');sensitivity=read(out/'sensitivity.json')
    description='''# Study0 Shot1↔Shot3：全部已匹配框的数值配准

## 结论

已用冻结图中16组匹配静态实体求得一组稳定的全局旋转、平移、统一尺度变换。旧流程只有2个合格锚点，没有生成任何配准假设；本次所有16组都参与拟合，无需Codex输出坐标变换。两组未匹配实体（门、灰靠垫）原样保留，未并入拟合或记为消失。

## 固定实验定义

输入固定为study01_gs_v12_20260915/study0/gs_v11/{graph_a,graph_b,matching}.json。这是原评分所用图，而非后续Shot1单独重跑结果。实体匹配、动静态标签、原始三维框与相机均不修改。

只优化一个共享变换 T(x)=sRx+t，s>0、det(R)=+1。每对OBB比较八角点均方距离，枚举24种保持手性的长方体等价角点编号，避免轴编号造成假误差。每个实体初始权重相同；无逐物体移动、自由形变或为降低误差重新匹配身份。

令e_i为第i对框的八角点RMS距离除以场景基准长度L。最小化mean_i Huber(e_i, δ)，主设置δ=0.05，同时预设检查0.025/0.1。L为目标图匹配实体中心两两距离的中位数。δ是诊断超参数，不是冲突阈值或校准置信度。通过三实体中心变换生成起点，选择8个起点执行角点对应更新及按实体Huber加权的迭代最小二乘。多起点收敛不代表证明全局最优。

## 对齐误差

所有百分比均为几何距离/L，不是一致性得分。第一行仅是不施加额外变换的基线，不能解释为真实物理移动。

| 方法 | 全部角点RMSE / L | 每实体角点误差中位数 / L |
|---|---:|---:|
'''
    names={'identity':'不施加变换','center_least_squares':'仅中心最小二乘','box_least_squares':'完整框最小二乘','box_huber':'完整框鲁棒拟合（主设置）'}
    for k,label in names.items():
        metrics=fits[k]['metrics'];description+=f"| {label} | {100*metrics['normalized_corner_rmse']:.3f}% | {100*metrics['normalized_corner_median']:.3f}% |\n"
    t=summary['robust_transform'];improvement=1-fits['box_huber']['metrics']['corner_rmse']/fits['identity']['metrics']['corner_rmse']
    description+=f"\n主结果角点RMSE下降{100*improvement:.2f}%。尺度s={t['scale']:.9f}，旋转角{t['rotation_angle_deg']:.6f}°，平移t={t['translation_b']}。L={baseline:.9f}，长度单位为输入模型坐标单位，非测量得到的真实米。完整旋转矩阵见fits.json。此变换修正两图坐标差异，不等于真实相机发生了上述运动。\n"
    description+='''
## 每次留出一个实体

对每个实体，用另外15个实体重新拟合，再计算被留出实体误差；被测实体不参与该次拟合或起点选择。其他实体中可能有同支撑/组成关系，因此这也不等同于16个统计独立样本。

| 实体 | 不施加变换误差/L | 全体拟合误差/L | 留出该实体误差/L |
|---|---:|---:|---:|
'''
    for row in loo:description+=f"| {row['group_id']} {row['name']} | {row['raw']/baseline*100:.2f}% | {row['fitted']/baseline*100:.2f}% | {row['heldout_normalized_corner_rmse']*100:.2f}% |\n"
    description+=f"\n留出误差总体RMSE/L={summary['loo_corner_rmse']/baseline*100:.3f}%，中位数/L={summary['loo_normalized_corner_median']*100:.3f}%。16次拟合的尺度范围{summary['loo_scale_range']}；相对全体拟合的旋转最大变化{summary['loo_rotation_deviation_max_deg']:.3f}°；其余实体中心预测最大变化为L的{summary['loo_other_prediction_shift_max']*100:.3f}%。8个起点最终预测差异最大为L的{summary['start_solution_spread']:.3g}。\n"
    description+='''
## 稳定性与真实变化被吸收的检查

本例普通最小二乘与鲁棒拟合的总体误差接近；不能声称鲁棒方法在该真实样本上的总体RMSE更优。三个δ设置得到相近的尺度和旋转。反向独立拟合后往返最大角点偏差为L的'''+f"{sensitivity['reverse_roundtrip_max_corner_error_normalized']*100:.3f}%。\n"
    ss=stress['results']
    description+=f"\n另做合成干预：只在目标图中把杯子平移0.5L。普通最小二乘导致其他实体预测平均漂移{ss['box_least_squares']['other_entities_mean_prediction_drift_normalized']*100:.3f}%L；鲁棒方法为{ss['box_huber']['other_entities_mean_prediction_drift_normalized']*100:.3f}%L。鲁棒方法仍保留杯子{ss['box_huber']['moved_entity_normalized_residual']*100:.3f}%L的大残差，没有把其运动整体吸收。此为合成测试，不是视频里观察到的杯子移动，也不证明各种真实变化均可检出。\n"
    description+='''
## 解释与下一步

现在可以向下游提供明确的数值变换、逐实体留出残差和稳定性信息，解决旧流程因锚点不足完全缺少变换的问题。但误差不为零：杯子、上层竖排书、台灯的留出残差相对较大，可能包含单目深度/形状误差；不能据此直接判定它们发生变化。

本次没有把新变换伪装成旧版trusted标志，也没有重跑Codex复核或改写Gs一致性评分。旧score=null继续保留。合理的后续是把这套数值配准证据接入复核，并验证它能否提高相容覆盖且保留已知冲突；当前结果仅证明这对图存在稳定、显著改善框匹配误差的数值解。

## 验证与查看

5项测试通过：已知Sim(3)恢复、24种角点等价表示、异常框保留及鲁棒性、共线退化拒绝、反射拒绝和反向/留出恢复（部分合并在同一测试中）。直接角点枚举重算、16项留出残差重算、杯子独立留出重拟合、中心差分驻点检查（梯度范数<1e-6；独立BFGS未进一步降低目标，但其求解器因精度问题未报告成功）、原图/匹配哈希均通过，见audit.json。原始图和评分未修改，无新模型/GPU调用；已有185272/node241单CPU执行。

[交互式对齐前后3D框](alignment.html) · [结果摘要](summary.json) · [逐实体留出检查](leave_one_out.json) · [合成移动测试](synthetic_movement.json)。交互网页已核对数据绑定，未执行浏览器交互测试。
'''
    (out/'RESULT.md').write_text(description)
    render(out,a,b,m,inp,loo,baseline)
    print(json.dumps(audit,ensure_ascii=False))

def render(out,a,b,m,inp,loo,baseline,case_title='Study0',notice=''):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from plotly.offline import get_plotlyjs
    fig=make_subplots(rows=1,cols=2,specs=[[{'type':'scene'},{'type':'scene'}]],subplot_titles=['对齐前：原坐标','对齐后：统一变换'])
    edges=[(i,j) for i in range(8) for j in range(i+1,8) if (i^j) in [1,2,4]]
    ids=[]
    for column,aa in [(1,a),(2,reg.transform(a,m))]:
        for i,name in enumerate(inp['names']):
            for label,boxes,color in [('Shot1',aa,'#2077b4'),('Shot3',b,'#e87517')]:
                pts=[]
                for u,v in edges:pts.extend([boxes[i,u].tolist(),boxes[i,v].tolist(),[None]*3])
                xyz=list(zip(*pts))
                fig.add_trace(go.Scatter3d(x=xyz[0],y=xyz[1],z=xyz[2],mode='lines',line=dict(color=color,width=4),
                              name=label,legendgroup=label,showlegend=(i==0 and column==1),text=name,
                              hovertemplate=name+'<extra>'+label+'</extra>'),row=1,col=column)
                ids.append(i)
    allpoints=np.concatenate([a.reshape(-1,3),b.reshape(-1,3),reg.transform(a,m).reshape(-1,3)])
    low,high=allpoints.min(0),allpoints.max(0);pad=(high-low)*.06
    scene=dict(aspectmode='data',xaxis=dict(title='X',range=[low[0]-pad[0],high[0]+pad[0]]),
               yaxis=dict(title='Y',range=[low[1]-pad[1],high[1]+pad[1]]),zaxis=dict(title='Z',range=[low[2]-pad[2],high[2]+pad[2]]),
               camera=dict(up=dict(x=0,y=0,z=1),eye=dict(x=1.5,y=-1.8,z=1.0)))
    buttons=[dict(label=f'全部{len(a)}组',method='update',args=[dict(visible=[True]*len(ids))])]
    buttons += [dict(label=f"{inp['groups'][i]['group_id']} {name}",method='update',args=[dict(visible=[j==i for j in ids])]) for i,name in enumerate(inp['names'])]
    fig.update_layout(height=660,margin=dict(l=5,r=5,b=5,t=80),scene=scene,scene2=scene,
                      updatemenus=[dict(buttons=buttons,x=0,y=1.12)],legend=dict(x=.8,y=1.1))
    plot=fig.to_html(full_html=False,include_plotlyjs=False,div_id='alignment')
    rows=''.join(f"<tr><td>{html.escape(x['name'])}</td><td>{100*x['raw']/baseline:.2f}%</td><td>{100*x['fitted']/baseline:.2f}%</td><td>{100*x['heldout_normalized_corner_rmse']:.2f}%</td></tr>" for x in loo)
    page='<!doctype html><meta charset="utf-8"><title>Study0 数值框配准</title><style>body{font:15px system-ui;margin:24px;color:#182638}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}</style><script>'+get_plotlyjs()+'</script><h1>Study0 Shot1 ↔ Shot3：数值配准</h1><p>蓝色 Shot1，橙色 Shot3。两图使用相同坐标范围；可旋转、缩放并选择单个实体。后图对所有Shot1框应用同一变换，实体身份和尺寸比例固定。</p>'+plot+'<p>误差为每框八角点RMS距离除以场景基准长度；不是一致性得分。留出误差由其他15个实体拟合后计算。</p><table><tr><th>实体</th><th>对齐前</th><th>全体拟合</th><th>留出该实体</th></tr>'+rows+'</table>'
    page=page.replace('Study0',html.escape(case_title)).replace('其他15个实体',f'其他{len(a)-1}个实体')
    if notice:page=page.replace('<h1>',f'<p style="color:#a83220;font-weight:600">{html.escape(notice)}</p><h1>',1)
    (out/'alignment.html').write_text(page)
    save(out/'viewer_audit.json',dict(status='pass',trace_count=len(ids),entities=len(a),source_and_target_boxes=2*len(a),
        equal_axis_ranges=True,all_transformed_source_boxes_single_model=True,original_frame_images_embedded=False,browser_execution_tested=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('out',type=Path);main(parser.parse_args().out)
