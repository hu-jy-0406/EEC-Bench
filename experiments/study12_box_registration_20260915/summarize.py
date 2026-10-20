"""Write a compact comparison without changing any fitted result."""
import json,math
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
def read(p):return json.loads(p.read_text())
paths={'study0':BASE.parent/'study0_box_registration_20260915/run01','study1':BASE/'study1','study2':BASE/'study2'}
rows=[]
for name,p in paths.items():
 s=read(p/'summary.json');t=s['robust_transform'];sens=read(p/'sensitivity.json')
 rows.append(dict(case=name,matched=s['matched_entities'],scale=t['scale'],rotation_deg=t['rotation_angle_deg'],
                  translation=t['translation_b'],translation_norm=math.sqrt(sum(x*x for x in t['translation_b'])),
                  rmse_before=s['methods']['identity']['normalized_corner_rmse'],
                  rmse_after=s['methods']['box_huber']['normalized_corner_rmse'],
                  loo_rmse=s['loo_corner_rmse']/s['baseline'],loo_rotation_max_deg=s['loo_rotation_deviation_max_deg'],
                  up_angle_deg=math.degrees(math.acos(max(-1,min(1,t['R_b_from_a'][2][2])))),
                  reverse_roundtrip=sens['reverse_roundtrip_max_corner_error_normalized'],baseline=s['baseline']))
(BASE/'comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
text='''# Study1 / Study2 Shot1→Shot3：同方法数值配准对照

## 结论

- **Study1 得到稳定的数值对齐候选**：近单位尺度、小旋转，留出某个实体后，变换与其余框的预测变化较小。台灯缺失不参与拟合，原未匹配记录保留。
- **Study2 当前未得到可直接采纳的物理对齐**：虽有收敛的数值解，但残差较大，而且将双方约定的向上方向几乎翻转。小目标函数值或数值求解成功不自动等于合理坐标变换。
- 两次运行与已完成的 Study0 使用字节相同的求解器、运行器及参数，不跨 case 使用实体、锚点或变换。只做数值配准，没有重算 Gs 一致性分数。

Study2 为旧称 Study3 的测例，目录 study_inconsistent_3；Study1 为 study_inconsistent_2。Study1 用原854×480输入所得冻结图，Study2用原852×480图；没有重新缩放或重做检测。每例仅比较自身 Shot1、Shot3。

## 主结果

单一变换 T(x)=sRx+t；s>0，det(R)=+1；全部明确匹配静态框参与，按实体八角点 RMS 的 Huber 损失拟合，δ=0.05。实体对应固定，没有逐实体形变。列中的误差均为角点RMSE除以本例场景基准长度L，**不是一致性得分**；各例的归一化L独立计算。

| 测例 | 匹配组数 | 尺度s | 旋转角 | 对齐前误差/L | 对齐后误差/L | 留出误差/L |
|---|---:|---:|---:|---:|---:|---:|
'''
for r in rows:text+=f"| {r['case']} | {r['matched']} | {r['scale']:.6f} | {r['rotation_deg']:.3f}° | {100*r['rmse_before']:.2f}% | {100*r['rmse_after']:.2f}% | {100*r['loo_rmse']:.2f}% |\n"
text+='\nStudy0 为已有参考结果，未重跑。留出误差：逐一排除被测实体，用其余实体拟合后再测它。\n\n| 测例 | 平移向量t=(x,y,z) | 平移范数 | 留出拟合旋转最大变化 | 向上方向旋转角 |\n|---|---|---:|---:|---:|\n'
for r in rows:text+=f"| {r['case']} | ({', '.join(f'{v:.6f}' for v in r['translation'])}) | {r['translation_norm']:.6f} | {r['loo_rotation_max_deg']:.3f}° | {r['up_angle_deg']:.3f}° |\n"
text+='''
平移为模型坐标单位，不是实测米；它表示坐标配准参数，不能解释为视频中相机实际平移。

## Study1

17 组明确匹配参与拟合，1 组未匹配台灯原样保留。尺度约放大2.97%、旋转0.173°；留出误差6.96%与全体拟合6.63%接近。留出拟合的旋转最大变化0.226°、其他实体中心预测最大变化0.978%L，反向往返最大误差0.437%L。

上层书组留出误差23.27%L，杯子10.16%L，明显高于多数实体；不能只报全局平均然后认定所有对象相容。残差可能有单目几何误差，尚未执行视觉复核。原台灯缺失不会因为其余17组对齐而被消除。

## Study2

11 组明确匹配参与拟合；另外12组unmatched、1组ambiguous、1组scope_mismatch均保持原样、不进入优化。相比Study1，可用于固定匹配的组更少，视角和图几何也不同；不能把该对比视作仅一个变量的因果实验。

自由三维旋转的数值解为176.069°，其中向上方向被转了175.181°（Rzz=-0.996464）。两侧输入均明确定义Z向上，因此这个解违反了已知的方向约定。det(R)=+1仅禁止镜像；绕水平轴转约180°仍是合法旋转，当前优化目标没有重力约束，允许选择这种降低框残差的方向。

对齐后RMSE34.74%L仍高；留出RMSE43.95%L，留出拟合最大旋转变化9.905°，其他实体中心预测最大变化16.158%L；反向独立拟合的往返最大误差17.527%L。不同起点收敛到相近解，不能弥补方向与稳定性问题。

本次不能据此断言“Study2所有这些残差都是视频不一致”，也不能断言不存在合理配准。现有冻结三维框/匹配、真实场景变化和目标缺少方向约束都可能影响结果。后续有针对性的改进是约束两图向上方向相容，再比较其残差与逐实体几何；该变体尚未运行，本报告保持与Study0相同的主设置。

## 验证与文件

两例的4种方法角点误差、共28项留出残差、各1项独立留出重拟合、源文件哈希、正尺度与正交旋转、目标单调性均通过。独立局部优化没有明显改善主目标；中心差分梯度范数分别2.37e-9、2.80e-8。Study1独立BFGS报告precision loss，已明确保存；不能声称其优化器success=true或全局最优。

数值求解器沿用Study0已通过5项合成测试的同一版本，本次未重复测试。审计也独立标记了Study2物理方向不合格；“数值审计通过”不代表“物理配准通过”。全部拟合/审计使用已有Slurm185272/node241单CPU，无新GPU资源或模型调用。交互网页已核对数据与标签，未做浏览器交互测试。

- [Study1详细报告](study1/RESULT.md) · [3D对齐前后](study1/alignment.html) · [完整变换与误差](study1/fits.json)
- [Study2详细报告](study2/RESULT.md) · [3D对齐前后](study2/alignment.html) · [完整变换与误差](study2/fits.json)
- [比较数值](comparison.json) · [验证与报告脚本](audit_report.py)
'''
(BASE/'RESULT.md').write_text(text)
print('comparison and RESULT.md written')
