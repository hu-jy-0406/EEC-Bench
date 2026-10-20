"""Independent read-back audit of all native scripts and actual tokenizer paths."""
import csv
import hashlib
import importlib.util
import json
import os
import socket
import statistics
import time
import zipfile
from pathlib import Path

import json5

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXP = ROOT / 'EECBench/experiments'
DEST = HERE / 'deliverables'
FEAS = EXP / 'generation_feasibility_20260921'


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def main():
    start = time.monotonic()
    assert socket.gethostname().startswith('auh7-1b-gpu-')
    assert len(os.sched_getaffinity(0)) == 1
    assert os.environ.get('USE_TORCH') == '0'
    assert os.environ.get('HF_HUB_OFFLINE') == '1'
    build = read(HERE / 'build_audit.json')
    for path, expected in build['source_hashes'].items():
        assert sha(Path(path)) == expected
    current = rows(EXP / 'source_video_priority_20260921/generation_queue_400.jsonl')
    wan = rows(EXP / 'wan_prompt_adaptation_20260921/deliverables/generation_queue_400.jsonl')
    queue = rows(DEST / 'generation_queue_400.jsonl')
    assert len(queue) == len(current) == len(wan) == 400
    assert queue == read(DEST / 'index.json')['episodes']
    assert len(list((DEST / 'episodes').glob('*/story_script.json'))) == 400
    assert [e['episode_id'] for e in queue] == [e['episode_id'] for e in current] == [e['episode_id'] for e in wan]
    for name, expected in [('core_100', queue[:100]), ('priority_200', queue[:200]),
                           ('stage2_additional_100', queue[100:200]), ('stage3_remaining_200', queue[200:])]:
        assert rows(DEST / (name + '.jsonl')) == expected
        assert [e['episode_id'] for e in expected] == [e['episode_id'] for e in rows(
            EXP / 'source_video_priority_20260921' / (name + '.jsonl'))]
    texts, counts, evidence_count, unchanged = [], [], 0, 0
    resumed_location_episodes = []
    native_scene_count = 0
    for rank, (entry, src, prior) in enumerate(zip(queue, current, wan), 1):
        eid = src['episode_id']
        assert entry['generation_priority'] == rank
        assert entry['shot_count'] == src['shot_count']
        assert entry['target_duration_seconds'] == src['target_duration_seconds']
        path = DEST / entry['story_script_path']
        assert path.resolve() == DEST / 'episodes' / eid / 'story_script.json'
        assert sha(path) == entry['story_script_sha256']
        # This is the parser used by the deployed StoryMem pipeline, not a
        # separately designed generation schema.
        with path.open() as f:
            story = json5.load(f)
        assert set(story) == {'story_name', 'story_overview', 'scenes'}
        assert story['story_name'] == src['title']
        assert story['story_overview'] == src['global_prompt']
        assert [s['scene_num'] for s in story['scenes']] == list(range(1, len(story['scenes']) + 1))
        generated_order = []
        for scene in story['scenes']:
            assert set(scene) == {'scene_num', 'video_prompts', 'cut'}
            assert len(scene['cut']) == len(scene['video_prompts']) > 0
            for i, prompt in enumerate(scene['video_prompts'], 1):
                assert type(scene['cut'][i - 1]) is bool and scene['cut'][i - 1]
                assert isinstance(prompt, str) and prompt.strip()
                generated_order.append((scene['scene_num'], i, prompt))
        assert len(generated_order) == src['shot_count'] == len(entry['shots'])
        assert story['scenes'][0]['video_prompts'][0] == generated_order[0][2]
        # The T2V invocation emits the first row, the M2V invocation skips
        # exactly (scene_num=1, shot_num=1) and preserves all remaining rows.
        assert [x for x in generated_order if x[:2] != (1, 1)] == generated_order[1:]
        contract_path = Path(entry['contract_path'])
        assert sha(contract_path) == entry['contract_sha256']
        contract = read(contract_path)
        assert contract['prompt']['global_prompt'] == src['global_prompt']
        available = {'global': src['global_prompt']}
        run_number, previous_source_scene, runs = 0, None, []
        for pos, (actual, mapping, shot, oldshot, cshot) in enumerate(zip(
                generated_order, entry['shots'], src['shots'], prior['shots'], contract['prompt']['shots'])):
            sid = shot['shot_id']
            assert mapping['shot_id'] == sid == oldshot['shot_id'] == cshot['shot_id']
            assert mapping['source_scene_id'] == shot['scene_id'] == oldshot['scene_id']
            assert mapping['contract_schedule_key'] == cshot['schedule_key']
            assert cshot['schedule_key'] in contract['entity_schedule']
            assert cshot['text'] == shot['generation_prompt_en']
            if shot['scene_id'] != previous_source_scene:
                runs.append(shot['scene_id'])
                run_number += 1
                local_shot = 1
            else:
                local_shot += 1
            previous_source_scene = shot['scene_id']
            assert actual[:2] == (run_number, local_shot)
            assert actual[:2] == (mapping['storymem_scene_num'], mapping['storymem_shot_num'])
            assert mapping['storymem_output_name'] == f'{run_number:02d}_{local_shot:02d}.mp4'
            assert mapping['target_duration_seconds'] == shot['target_duration_seconds'] == 5
            assert mapping['cut'] is True
            additions = oldshot['context_additions']
            wanted = shot['generation_prompt_en']
            if additions:
                wanted += ' ' + ' '.join(a['text'] for a in additions)
            assert actual[2] == wanted
            assert mapping['prompt_sha256'] == digest(wanted)
            assert mapping['current_source_prompt_sha256'] == digest(shot['generation_prompt_en'])
            assert mapping['context_additions_count'] == len(additions)
            for a in additions:
                assert a['target_quote'] in shot['generation_prompt_en']
                for ev in a['evidence']:
                    assert ev['source_shot_id'] in available
                    assert ev['quote'] and ev['quote'] in available[ev['source_shot_id']]
                    evidence_count += 1
            available[sid] = shot['generation_prompt_en']
            unchanged += wanted == oldshot['wan_prompt_en']
            texts.append(wanted)
            counts.append(mapping['tokens_including_special'])
        native_scene_count += len(runs)
        if len(set(runs)) < len(runs):
            resumed_location_episodes.append(eid)
    assert len(texts) == 2000 and unchanged == 1999
    assert evidence_count == build['current_exact_evidence_references']
    module_path = FEAS / 'repos/StoryMem/wan/modules/tokenizers.py'
    spec = importlib.util.spec_from_file_location('verified_storymem_tokens', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import transformers
    for model in ['Wan2.2-T2V-A14B', 'Wan2.2-I2V-A14B']:
        token_path = FEAS / 'models' / model / 'google/umt5-xxl'
        tok = module.HuggingfaceTokenizer(str(token_path), seq_len=512, clean='whitespace', local_files_only=True)
        # Match production padding/truncation, retaining a plain CPU list to
        # avoid loading torch. Compare every nonpadding ID with unlimited text.
        padded, masks = tok(texts, return_tensors=None, return_mask=True, add_special_tokens=True)
        unlimited = tok(texts, return_tensors=None, padding=False, truncation=False,
                        add_special_tokens=True, return_attention_mask=False)
        effective = [[token for token, keep in zip(ids, mask) if keep] for ids, mask in zip(padded, masks)]
        assert effective == unlimited
        assert all(len(ids) == 512 for ids in padded)
        assert list(map(len, unlimited)) == counts and max(counts) <= 512
    csv_rows = list(csv.DictReader((DEST / 'token_audit.csv').open()))
    flat_ids = [(s['episode_id'], t['shot_id']) for s in current for t in s['shots']]
    assert len(csv_rows) == 2000
    for rec, ids, n, text in zip(csv_rows, flat_ids, counts, texts):
        assert (rec['episode_id'], rec['shot_id']) == ids
        assert int(rec['tokens_including_special']) == n and rec['prompt_sha256'] == digest(text)
    for path, expected in build['source_hashes'].items():
        assert sha(Path(path)) == expected
    validation = {'status': 'pass', 'episodes': 400, 'shots': 2000,
        'native_json5_loader_and_generation_order': 'pass', 'all_cut_values_are_boolean_true': True,
        'current_source_and_contract_text_match': True, 'reviewed_context_suffixes_unchanged': True,
        'current_exact_evidence_references': evidence_count, 'unchanged_final_shots': unchanged,
        'source_shot_and_persistent_scene_mapping': 'pass', 'nested_subset_order': 'pass',
        'resumed_location_episodes': resumed_location_episodes, 'native_scene_occurrences': native_scene_count,
        't2v_and_m2v_production_nonpadding_ids_equal_untruncated': True,
        'tokens_including_special': {'min': min(counts), 'max': max(counts), 'mean': statistics.mean(counts), 'over_512': 0},
        'transformers_version': transformers.__version__, 'seconds': time.monotonic() - start,
        'new_model_calls': 0, 'billable_api_tokens': 0, 'api_usd': 0, 'gpu_work': False,
        'generation_started': False, 'fresh_model_semantic_review': False}
    dump(HERE / 'independent_validation.json', validation)
    report = f'''# StoryMem prompt 数据：400 条完成

每条 episode 一份 `deliverables/episodes/<episode_id>/story_script.json`，可直接作为官方 `pipeline.py --story_script_path` 的输入。保留原 400 条优先队列、2,000 个 shot、每 shot 5 秒目标时长，以及 Core100 ⊂ Priority200 ⊂ Full400。

沿用已独立复核的 Wan 上下文补全：1,084 个 shot 的 1,644 项补充逐字保留。采用当前原始 prompt 修订版；3 条 episode 中更新 1 处 shot 正文和 2 处全局摘要。1,999 个最终 shot 文本与此前 Wan 输入逐字相同。最终生成脚本只含当前文本，没有旧矛盾版本或修改解释。

## 输入和映射

- 原生字段：`story_name`、`story_overview`、`scenes`；每个 scene 包含 `scene_num`、`video_prompts`、`cut`。
- `story_overview` 保存当前 global 摘要，官方生成模型只读取当前 `video_prompts` 项。已补全正文直接使用，不要再次追加 global、其他 shot、实体表或 claims。
- 当前数据集由独立镜头组成，全部 `cut` 为 JSON 布尔值 `true`，保留跨镜头视觉记忆，不强制从上一段末帧平滑延续。同一场景切换机位也保持 `true`。
- 按连续场景片段顺序编号，共 {native_scene_count} 个原生 scene 条目。{len(resumed_location_episodes)} 条 episode 有离开后返回同一场景的情况，保留原始镜头顺序。StoryMem 的序号表示生成顺序；评测的持久场景身份和 contract schedule key 保存在索引中，不从该序号重新推断。
- `deliverables/index.json` 和各队列 JSONL 记录脚本相对路径、原始 Shot ID、原始 scene ID、contract schedule key、原生镜头编号、预期视频文件名、文本及合同 hash。队列文件是调度索引；每个 `story_script.json` 才是模型原生输入。
- Core100 后只追加 `stage2_additional_100.jsonl`，再追加 `stage3_remaining_200.jsonl`；`priority_200.jsonl` 是累计集合。

## 校验

全量独立读回审计通过：400 个原生 JSON 使用官方同款 JSON5 parser 加载；T2V 首镜头与 M2V 后续迭代保持全部 2,000 个镜头顺序。当前原文、contract 文本、保留补充、1,821 条前文引用、场景及镜头映射、各子集和文件 hash 均通过检查。

使用实际 StoryMem tokenizer wrapper，以及已部署 T2V 和 I2V checkpoint 各自的 UMT5 tokenizer，在离线单 CPU 上分别验证。最终每 shot 含 special tokens 的长度为 {min(counts)}–{max(counts)}，平均 {statistics.mean(counts):.3f}；超过 512 的为 0。模拟实际 512 padding/truncation 后的全部有效 token IDs 与不截断编码完全一致。`token_audit.csv` 提供逐 shot 结果。

本次为确定性复用、版本同步和格式转换；语义补全依据已有完整独立模型复核，未重新进行模型语义审查，也不等同独立人工标注。现有评测 contract 和旧 Wan 生成历史保持其版本记录；StoryMem 使用本次交付的新输入。

本次新增模型调用 0、计费 API tokens 0、API USD 0（不含父对话及既有 Wan 补全费用）。CPU-only，复用已有 allocation206117/node306 的一个已检查空闲 CPU，未运行视频生成或申请新资源。

详细检查：`independent_validation.json`；来源与 tokenizer hash：`build_audit.json`。原始配置和代码依据为本地已测试 StoryMem checkout；原生示例见 https://github.com/Kevin-thu/StoryMem/blob/main/story/black.json 。
'''
    (HERE / 'REPORT.md').write_text(report)
    artifacts = {str(p.relative_to(DEST)): sha(p) for p in sorted(DEST.rglob('*')) if p.is_file() and p.name != 'sha256.json'}
    dump(DEST / 'sha256.json', artifacts)
    archive = HERE / 'storymem_prompts_400.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(DEST.rglob('*')):
            if p.is_file():
                z.write(p, str(p.relative_to(HERE)))
        for name in ['REPORT.md', 'build_audit.json', 'independent_validation.json', 'build.py', 'verify.py']:
            z.write(HERE / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        archive_entries = len(z.namelist())
    (HERE / 'storymem_prompts_400.zip.sha256').write_text(sha(archive) + '  ' + archive.name + '\n')
    complete = dict(validation, status='complete', archive=str(archive), archive_bytes=archive.stat().st_size,
                    archive_entries=archive_entries, archive_sha256=sha(archive), completed=time.time())
    dump(HERE / 'completion.json', complete)
    print(json.dumps(complete, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
