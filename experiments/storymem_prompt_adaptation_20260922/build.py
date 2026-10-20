"""Reuse reviewed context additions and export native StoryMem story scripts.

Run offline on one checked CPU in an existing compute allocation. No model
inference, prompt rewriting, source-video access, or historical-input mutation.
"""
import csv
import hashlib
import importlib.util
import json
import os
import socket
import statistics
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXP = ROOT / 'EECBench/experiments'
PRIOR = EXP / 'source_video_priority_20260921'
WAN = EXP / 'wan_prompt_adaptation_20260921'
CONTRACTS = EXP / 'episode_contracts_20260921'
FEAS = EXP / 'generation_feasibility_20260921'
REPO = FEAS / 'repos/StoryMem'
DEST = HERE / 'deliverables'


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def safe_cpu():
    assert socket.gethostname().startswith('auh7-1b-gpu-')
    assert len(os.sched_getaffinity(0)) == 1
    assert os.environ.get('USE_TORCH') == '0'
    assert os.environ.get('TOKENIZERS_PARALLELISM') == 'false'
    assert os.environ.get('HF_HUB_OFFLINE') == '1'


def tokenizer():
    spec = importlib.util.spec_from_file_location('storymem_tokens', REPO / 'wan/modules/tokenizers.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.HuggingfaceTokenizer


def main():
    started = time.monotonic()
    safe_cpu()
    assert not DEST.exists(), 'Refuse to overwrite an existing delivery.'
    source_path = PRIOR / 'generation_queue_400.jsonl'
    wan_path = WAN / 'deliverables/generation_queue_400.jsonl'
    source_hashes = {str(p): sha(p) for p in [source_path, wan_path,
        CONTRACTS / 'source_revision.json', WAN / 'independent_validation.json']}
    source, old = rows(source_path), rows(wan_path)
    old_audit = read(WAN / 'independent_validation.json')
    assert old_audit['status'] == 'pass'
    assert sha(wan_path) == old_audit['artifact_hashes'][wan_path.name]
    revision = read(CONTRACTS / 'source_revision.json')
    assert sha(source_path) == revision['queue_sha256']
    assert len(source) == len(old) == 400
    assert [e['episode_id'] for e in source] == [e['episode_id'] for e in old]
    scripts, index, records, contexts = [], [], [], []
    changed_episodes, global_updates, shot_updates = set(), [], []
    refs = 0
    for rank, (src, prior) in enumerate(zip(source, old), 1):
        eid = src['episode_id']
        assert prior['generation_priority'] == rank
        assert src['shot_count'] == prior['shot_count'] == len(src['shots'])
        assert src['target_duration_seconds'] == prior['target_duration_seconds']
        assert [s['shot_id'] for s in src['shots']] == [s['shot_id'] for s in prior['shots']]
        contract_path = CONTRACTS / 'deliverables/episodes' / eid / 'contract.json'
        contract = read(contract_path)
        cp = contract['prompt']
        assert cp['global_prompt'] == src['global_prompt']
        assert [(s['shot_id'], s['text']) for s in cp['shots']] == [
            (s['shot_id'], s['generation_prompt_en']) for s in src['shots']]
        if src['global_prompt'] != prior['global_prompt_original']:
            changed_episodes.add(eid)
            global_updates.append(eid)
        script = {'story_name': src['title'], 'story_overview': src['global_prompt'], 'scenes': []}
        entry = {'episode_id': eid, 'generation_priority': rank,
                 'shot_count': src['shot_count'], 'target_duration_seconds': src['target_duration_seconds'],
                 'story_script_path': f'episodes/{eid}/story_script.json',
                 'contract_path': str(contract_path), 'contract_sha256': sha(contract_path), 'shots': []}
        evidence_sources = {'global': src['global_prompt']}
        previous_scene = None
        for src_shot, wan_shot, contract_shot in zip(src['shots'], prior['shots'], cp['shots']):
            sid = src_shot['shot_id']
            raw = src_shot['generation_prompt_en']
            original = wan_shot['generation_prompt_en_original']
            additions = wan_shot['context_additions']
            suffix = (' ' + ' '.join(a['text'] for a in additions)) if additions else ''
            assert wan_shot['wan_prompt_en'] == original + suffix
            assert src_shot['scene_id'] == wan_shot['scene_id']
            assert src_shot['target_duration_seconds'] == wan_shot['target_duration_seconds'] == 5
            if raw != original:
                changed_episodes.add(eid)
                shot_updates.append({'episode_id': eid, 'shot_id': sid})
            for addition in additions:
                assert addition['target_quote'] and addition['target_quote'] in raw, (eid, sid, 'target')
                for ev in addition['evidence']:
                    assert ev['source_shot_id'] in evidence_sources, (eid, sid, 'future evidence')
                    assert ev['quote'] and ev['quote'] in evidence_sources[ev['source_shot_id']], (eid, sid, ev)
                    refs += 1
            final = raw + suffix
            evidence_sources[sid] = raw
            # A returning location must not move backward in generation order.
            # Native scene_num is an occurrence index; persistent source IDs
            # and contract keys stay in the external dispatch mapping.
            if src_shot['scene_id'] != previous_scene:
                script['scenes'].append({'scene_num': len(script['scenes']) + 1,
                                         'video_prompts': [], 'cut': []})
            scene = script['scenes'][-1]
            scene['video_prompts'].append(final)
            scene['cut'].append(True)
            previous_scene = src_shot['scene_id']
            position = len(scene['video_prompts'])
            mapping = {'shot_id': sid, 'source_scene_id': src_shot['scene_id'],
                       'contract_schedule_key': contract_shot['schedule_key'],
                       'storymem_scene_num': scene['scene_num'], 'storymem_shot_num': position,
                       'storymem_output_name': f"{scene['scene_num']:02d}_{position:02d}.mp4",
                       'target_duration_seconds': 5, 'cut': True,
                       'prompt_sha256': text_sha(final), 'current_source_prompt_sha256': text_sha(raw),
                       'context_additions_count': len(additions)}
            entry['shots'].append(mapping)
            records.append({'episode_id': eid, 'shot_id': sid, 'text': final,
                            'wan_text_changed': final != wan_shot['wan_prompt_en']})
            contexts.append({'episode_id': eid, 'shot_id': sid, 'context_additions': additions})
        scripts.append(script)
        index.append(entry)
    assert len(records) == 2000
    assert changed_episodes == set(revision['episode_ids'])
    assert len(global_updates) == 2 and len(shot_updates) == 1
    texts = [r['text'] for r in records]
    tok_class = tokenizer()
    tokenizer_records = {}
    lengths_by_model = {}
    for model in ['Wan2.2-T2V-A14B', 'Wan2.2-I2V-A14B']:
        path = FEAS / 'models' / model / 'google/umt5-xxl'
        tok = tok_class(str(path), seq_len=512, clean='whitespace', local_files_only=True)
        kw = dict(return_tensors=None, padding=False, add_special_tokens=True, return_attention_mask=False)
        full = tok(texts, truncation=False, **kw)
        production = tok(texts, **kw)
        assert full == production
        lengths = list(map(len, full))
        assert 0 < min(lengths) and max(lengths) <= 512
        lengths_by_model[model] = lengths
        tokenizer_records[model] = {'path': str(path), 'class': type(tok.tokenizer).__name__,
            'fast': tok.tokenizer.is_fast, 'files': {p.name: sha(p) for p in path.iterdir() if p.is_file()},
            'min': min(lengths), 'max': max(lengths), 'mean': statistics.mean(lengths),
            'over_512': 0, 'production_ids_equal_untruncated': True}
    assert lengths_by_model['Wan2.2-T2V-A14B'] == lengths_by_model['Wan2.2-I2V-A14B']
    lengths = lengths_by_model['Wan2.2-T2V-A14B']
    for item, n in zip((s for e in index for s in e['shots']), lengths):
        item['tokens_including_special'] = n
    for entry, script in zip(index, scripts):
        path = DEST / entry['story_script_path']
        dump(path, script)
        entry['story_script_sha256'] = sha(path)
    for name, selected in [('generation_queue_400', index), ('core_100', index[:100]),
                           ('priority_200', index[:200]), ('stage2_additional_100', index[100:200]),
                           ('stage3_remaining_200', index[200:])]:
        (DEST / (name + '.jsonl')).write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in selected))
        if name != 'generation_queue_400':
            assert [e['episode_id'] for e in selected] == [e['episode_id'] for e in rows(PRIOR / (name + '.jsonl'))]
    dump(DEST / 'index.json', {'schema_version': 'storymem_prompt_bundle_v1', 'episodes': index})
    # Reuse existing source-grounded provenance; no correction explanations in scripts.
    (HERE / 'context_provenance.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in contexts))
    with (DEST / 'token_audit.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=['episode_id', 'shot_id', 'tokens_including_special', 'prompt_sha256'])
        writer.writeheader()
        for rec, n in zip(records, lengths):
            writer.writerow({'episode_id': rec['episode_id'], 'shot_id': rec['shot_id'],
                             'tokens_including_special': n, 'prompt_sha256': text_sha(rec['text'])})
    for path, h in source_hashes.items():
        assert sha(Path(path)) == h, 'An input changed during export.'
    report = {'status': 'built_pending_independent_audit', 'episodes': 400, 'shots': 2000,
              'source_hashes': source_hashes, 'updated_episode_ids': sorted(changed_episodes),
              'global_updates': global_updates, 'shot_updates': shot_updates,
              'unchanged_final_shots': sum(not r['wan_text_changed'] for r in records),
              'context_additions': sum(len(c['context_additions']) for c in contexts),
              'shots_with_context_additions': sum(bool(c['context_additions']) for c in contexts),
              'current_exact_evidence_references': refs,
              'native_scene_occurrences': sum(len(s['scenes']) for s in scripts),
              'all_cut_flags_true': True, 'tokenizers': tokenizer_records,
              'storymem_wrapper_sha256': sha(REPO / 'wan/modules/tokenizers.py'),
              'pipeline_sha256': sha(REPO / 'pipeline.py'),
              'source_scripts': {p.name: sha(p) for p in HERE.glob('*.py')},
              'cpu_affinity': sorted(os.sched_getaffinity(0)), 'host': socket.gethostname(),
              'seconds': time.monotonic() - started, 'model_calls': 0, 'billable_api_tokens': 0,
              'api_usd': 0, 'gpu_work': False, 'generation_started': False}
    dump(HERE / 'build_audit.json', report)
    print(json.dumps({k: report[k] for k in ['status', 'episodes', 'shots', 'unchanged_final_shots',
          'context_additions', 'current_exact_evidence_references', 'native_scene_occurrences', 'seconds']}, indent=2))


if __name__ == '__main__':
    main()
