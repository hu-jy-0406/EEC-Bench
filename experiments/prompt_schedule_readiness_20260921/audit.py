#!/usr/bin/env python3
"""Small, read-only dataset audit; writes only this experiment's diagnostics."""
import collections
import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATA = ROOT / "EECBench/experiments/source_video_400_20260920/deliverables/candidates_400.jsonl"
CONTRACT = ROOT / "EECBench/experiments/prompt_alignment_four_dimensions_20260921/frozen/contract.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    before = sha(DATA)
    episodes = [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]
    stats = collections.Counter()
    errors = []
    episode_ids = set()
    for episode in episodes:
        eid = episode["episode_id"]
        stats["episodes"] += 1
        if eid in episode_ids:
            errors.append([eid, "duplicate_episode_id"])
        episode_ids.add(eid)
        shots = episode["shots"]
        entities = episode["entities"]
        shot_ids = [s["shot_id"] for s in shots]
        entity_ids = [e["entity_id"] for e in entities]
        stats["shots"] += len(shots)
        stats["source_entities"] += len(entities)
        stats["global_prompts"] += bool(episode.get("global_prompt", "").strip())
        stats["entity_shot_cells_if_existing_source_population_is_retained"] += len(shots) * len(entities)
        for field in ("entity_schedule", "registry", "prompt_registry", "claims", "contract"):
            stats["episodes_with_" + field] += field in episode
        for name, values in (("shot", shot_ids), ("entity", entity_ids)):
            if len(values) != len(set(values)):
                errors.append([eid, "duplicate_" + name + "_id"])
        by_entity = {e["entity_id"]: e for e in entities}
        for entity in entities:
            stats["source_entities_with_schedule"] += "schedule" in entity
            for occurrence in entity.get("occurrences", []):
                if occurrence["shot_id"] not in shot_ids:
                    errors.append([eid, entity["entity_id"], "unknown_source_occurrence_shot"])
        for shot in shots:
            sid = shot["shot_id"]
            stats["per_shot_prompts"] += bool(shot.get("generation_prompt_en", "").strip())
            stats["shots_with_entity_schedule"] += "entity_schedule" in shot
            for field in ("prompt_entity_ids", "visible_entity_ids"):
                stats["shots_with_" + field] += field in shot
                refs = shot.get(field, [])
                if len(refs) != len(set(refs)):
                    errors.append([eid, sid, field, "duplicate_reference"])
                for ref in refs:
                    if ref not in by_entity:
                        errors.append([eid, sid, field, "unknown_entity", ref])
            for ref in shot.get("prompt_entity_ids", []):
                if ref in by_entity and sid not in [v["shot_id"] for v in by_entity[ref].get("occurrences", [])]:
                    errors.append([eid, sid, ref, "prompt_id_without_source_occurrence"])
    contract = json.loads(CONTRACT.read_text())
    assert before == sha(DATA), "Source changed during audit"
    result = {
        "status": "structural_audit_complete_formal_schedule_and_claims_missing",
        "checked_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input": str(DATA), "input_sha256": before,
        "counts": dict(stats), "structural_errors": errors,
        "study3_reference": {
            "path": str(CONTRACT), "sha256": sha(CONTRACT),
            "registry_schema": contract["registry"]["schema_version"],
            "contract_schema": contract["schema_version"],
            "dimension_profile": contract["dimension_profile"],
            "prompt_entities": len(contract["registry"]["entities"]),
            "claims": len(contract["claims"]),
            "claim_counts": dict(collections.Counter(c["dimension"] for c in contract["claims"])),
            "claims_source": contract["claims_source"],
        },
        "scope": "Published 400-record package and selected Study3 reference; source metadata is not a text-only evaluation contract.",
        "semantic_coverage_validated": False,
        "model_calls": 0, "tokens": 0, "api_usd": 0,
        "production_files_changed": False,
        "limitations": [
            "Referential checks do not establish that every prompt-mentioned entity or requirement is represented.",
            "Source-frame facts, visible entities and occurrences must not silently become generation requirements.",
            "Unlisted source entities do not imply forbidden or physically absent entities.",
            "Study3's human-authored claims and fresh scoring do not validate automatic compilation of this dataset.",
            "No registry, schedule, claim, prompt, scoring rule or generated video was modified by this audit.",
        ],
    }
    (HERE / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    report = f"""# 400 条 prompt 的 schedule 就绪检查

检查时间：{result['checked_utc']}。仅做结构审计，没有模型调用或生产修改。

| 项目 | 数量 |
|---|---:|
| Episode / global prompt | {stats['episodes']} / {stats['global_prompts']} |
| Shot / per-shot prompt | {stats['shots']} / {stats['per_shot_prompts']} |
| 源视频实体记录 | {stats['source_entities']} |
| 带 prompt_entity_ids 的 shot | {stats['shots_with_prompt_entity_ids']} |
| 包含正式 registry 的 episode | {stats['episodes_with_registry'] + stats['episodes_with_prompt_registry']} |
| 源实体上的完整 schedule | {stats['source_entities_with_schedule']} |
| 包含 claims 的 episode | {stats['episodes_with_claims']} |
| ID/引用结构错误 | {len(errors)} |

全量原始 JSONL 未修改，SHA256：`{before}`。原包 deliverables 未交付独立冻结 schedule/contract。

## 已有格式

采用 `EECBench/docs/prompt-binding-v1.md` 与 `EECBench/docs/prompt-alignment-b-v1.md` 当前顶层四维规则。
`prompt_registry_v1` 包含 ordered shot_ids 和 episode 级实体 ID。每个实体包含 name、description、逐字 prompt evidence，以及覆盖每个 shot 的 schedule（shot_id、expectation、reason）。expectation 为 required / not_required / forbidden / unknown。

required 是镜头内应出现，不要求每帧可见；not_required 不构成不存在/禁止；forbidden 必须来自明确约束；unknown 保留真实歧义。实体 ID 跨整个 episode 共用，场景上下文及衣物属性不自动独立成实体。

`prompt_alignment_b_v1` + `four_dimensions_v1` 另保存原子 claims，维度仅 presence / appearance / spatial / motion。Schedule 本身不能替代颜色、空间关系、动作要求。required/forbidden 行必须对应存在/缺失 claim；其余要求须逐字文本证据、实体及 shot scope、量词、坐标系、依赖。

## Study3 验证范围

参照有9实体、79claims（18 presence / 28 appearance / 17 spatial / 16 motion），由人工文本编译。`study3_final_integrated_20260921/REPORT.md` 记录一次新完整评测；此前离线四维迁移是独立历史结果。最新 comparison_witnesses 绑定扩展仅CPU测试，未进行新完整模型运行。

这证明已有格式可以接入评测；不证明400条自动编译或4/6/8镜头批处理已经通过语义审计。

## 补齐建议（未执行生产编译）

1. 以真正给生成模型的 global+per-shot prompt 冻结 reference_text / facts；源帧说明和 uncertainties 仅保留为来源记录，不自动成为评分要求。
2. 沿用 episode 内实体 ID，保存源 ID 映射；按文本检查实体/实体粒度和完整逐-shot schedule，禁止从源图未出现直接推导 forbidden。
3. 使用现有四维 claim 编译与校验规则；普通外观 when_visible、存在 exists，静止/动作按实际文本，不恢复独立 temporal 维度。
4. 先以4/6/8shot样例验证文本编译的语义覆盖，再处理全400条并导出冻结contract、registry、narrative、hash及可读schedule。
5. 各模型prompt适配必须保留同一冻结实体/要求；短文本删掉了评分要求时，不能仍按完整要求评测并声称公平。

无需据此改写已选定的评分公式或Judge提示词。当前缺口是数据侧输入编译及审计。

本次新增0次模型调用、0tokens、USD0 API费用。
"""
    (HERE / "REPORT.md").write_text(report)
    print(json.dumps({"report": str(HERE / "REPORT.md"), "counts": dict(stats), "structural_errors": len(errors)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
