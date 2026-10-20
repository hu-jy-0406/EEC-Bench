> 状态更新：用户随后选择暂不融合；已实现并在Study2/Study3运行独立两分版本。当前协议见 entity-appearance-separate-v1.md。本文件融合公式未采用。

# Entity appearance：单次Codex评价与DINO融合方案

日期2026-09-20。用户已接受：一个global实体的全部appearance及相关剧情prompt进入一次Codex调用，通用多视角解释在这次调用内完成，输出一个实体Codex分数。当前请求是设计DINO/Codex融合与多实体汇总。本文中“单次全量Codex评价”记录用户已选方向；融合公式、权重与可比性附加字段是本次建议，尚未实施或视作用户已批准。

本文取代此前v1的逐对模型调用，以及v2/v3的额外视角描述调用、外置多参考评分图。仍保留通用部位/表面可比性、真实原图证据、未知不等于一致的原则。无生产prompt/评分代码变更，无模型调用，未计算新实验结果。

## EntityBench依据与本方案区别

查阅 https://arxiv.org/html/2605.15199v1#A2.SS4 ：EntityBench分别报告DINO中心相似度和VLM指标；其admissibility/fidelity gate及instance-weighted aggregation不是已发表的DINO×VLM融合公式。它的一项episode DINO指标按appearance汇集，原协议每entity-shot只有一个canonical crop；benchmark级还报告gate-corrected aggregation。不能把下述公式称为EntityBench原公式。

本方案借鉴“判断证据是否适用”和“按实体出现机会汇总”，不照搬prompt-fidelity筛除、未知/调用失败填零或新appearance的阈值。本指标衡量已确认实体出现的外观自一致性，不是文字描述符合度，也不是存在性/空间总分。

## 1. 固定输入与单次Codex输出

每个global实体给出所有正检测appearance的唯一ID、shot/frame/time、原图/crop及原bbox/候选来源，相关正常剧情事实。Codex一次性联合检查全部输入，身份不可改写；各种物体均比较可对应的可见部位/表面。不得把“另一个视角”当成无证据豁免，不能想象未展示表面；前胸/背面、包装盒正反面等不同表面的天然差异不可当成改变。集合证据要覆盖实际集合，不能把单成员框当整组。

四项内部维度：结构形状、颜色纹理材料外观、内在比例、独特细节。采用已讨论的0/25/50/75/100评分档及null，每项必须有原图证据，Code分C_e为非null维度均值。维度全部未知、仅一个有效appearance或无跨appearance可比属性时C_e=null；因视角看不到的部位不自动计100。预期合法变化仅豁免对应属性和时间，不在原始DINO中自动消除。

为融合建议在同一次响应增加：

```
{
  "score": 75,
  "dimension_scores": {"structure_shape": 100, "color_texture_material": 25,
                       "proportions": 100, "distinctive_details": null},
  "dino_comparability": {
    "status": "comparable | view_dependent | scope_mismatch | expected_change | uncertain",
    "reason": "...",
    "evidence_appearance_ids": ["A01", "A07"]
  },
  "reason": "..."
}
```

状态在真实schema中必须是单一枚举值。Codex不接收DINO数值、空间分数、历史判分或答案提示；程序校验维度均值、ID有效性、必需字段和全部输入清单。不能声称仅凭返回清单就证明模型已认真看过所有图；需人工校准。超上下文上限不能静默抽样。DINO和Codex使用同一已记录appearance population；处理失败/质量排除留明细，不秘密筛掉低分案例。

## 2. 可比性g_e

g_e=1仅当Codex有证据支持这批用于原始DINO中心分的crop在观察表面、角度、裁剪范围、遮挡和光照方面足够可比，使全crop embedding差异能作为外观差异的辅助证据。其余状态g_e=0；unknown不当作适用。

这不是“是否外观相同”的判断，也不是模型置信度权重。真实变色、换纹理、变形本身不得作为关闭g的理由；可比性应由观察条件确定。明显正背面/不同表面、整组与成员裁剪混用、大幅遮挡/光照变化或剧情明确授权的外观变化会使原始DINO缺少语义适用性，g=0。混合多视角实体首版保守地整体关闭DINO扣分，不只挑最容易的子集重算D。此限制牺牲部分DINO信息，优先避免已讨论的视角误罚；需要用人工样例校准gate。

即使g=0，Codex依然要检查有证据的外观冲突；绝不是全实体免罚。

## 3. 单实体融合（本次建议）

D_e为此前选定的原始DINO中心平均分(0–1)，原数不更改；C_e为上述Codex分(0–100)。建议首版固定lambda=0.25：

F_e = C_e - lambda * g_e * max(0, C_e - 100*D_e)

等价于 min(C_e, (1-lambda*g_e)*C_e + lambda*g_e*100*D_e)。

- g=0：F=C，低DINO不造成多视角误罚。
- g=1且100D<C：F=0.75C+0.25(100D)。
- 100D>=C：F=C，高embedding相似度不能抬高已判较低的语义外观分。
- 对有效数值：0<=F<=C<=100，对D/C均单调不减；DINO最多扣除当前Codex分的25%。

0.25是明确待验证的首版超参数，不来自EntityBench，也不是已校准概率融合。此规则有意让Codex主判，不能用DINO高分纠正Codex误判；必须检验Codex误报率与gate质量。DINO和Codex可能重复捕捉同一缺陷，本式是保守排序启发式，不声称统计独立或避免所有重复扣分。校准前不宣称最终数字代表人类正确率。

示例（说明公式，非实测）：

| 情况 | D | C | g | F |
|---|---:|---:|---:|---:|
| 正背面不同，但可比属性一致 | .75 | 100 | 0 | 100 |
| 视角接近，外观稳定 | .95 | 100 | 1 | 98.75 |
| DINO很高，但有明确局部外观改变 | .98 | 50 | 1 | 50 |
| 可比图像中两者都提示变化 | .60 | 75 | 1 | 71.25 |

100只指可判外观属性一致；没有被看到的脸/表面等仍在unknown记录中。

## 4. Episode汇总（本次建议）

w_e取全局表中该实体确定出现的不同shot数，不取关键帧数量、DINO分、模型置信度或评分成功次数。这样近似继承EntityBench每entity-shot一次appearance的权重，同时避免同一shot抽更多关键帧便抬高权重。只在一个shot出现但有>=2有效关键帧仍可评shot内外观，w=1；它不产生跨shot证据。

F_episode = sum_{e in E_valid}(w_e * F_e) / sum_{e in E_valid}(w_e)

E_valid为F_e非null的实体。没有有效实体返回null。不把单例或不可评实体计100或0；单独记录全部实体数、可评实体数、不可评原因及有效/总权重。此处是conditional appearance score，不照搬EntityBench benchmark级gate-corrected零贡献规则；不能把少量有效实体的高分解释成全episode全部实体已验证。仍保留每实体D/C/g/F，便于定位和审计。不与现有presence/spatial混成总分。

DINO缺失而Codex有效：F=C并标fusion_mode=codex_only_dino_missing。Codex失败或全未知：F=null，D仅保留诊断，不悄悄改成DINO单模态最终分。保存正常g=0的codex_only_observation_conditions模式与运算失败区别。

## 5. 后续校准

先固定lambda=.25及上述规则，用已讨论的多类物体、多视角、真实改变、遮挡和集合裁剪样例评估；对lambda=0/.25/.5作离线敏感性比较，选定后冻结，不按每个模型/episode追逐更好分数。视角gate误把真实缺陷关闭和Codex因无法观察而误给高分应单独检查。当前未运行任何新评测。
