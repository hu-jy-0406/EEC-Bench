#!/usr/bin/env python3
"""Freeze the canonical five-model scoring cohort in generation-priority order."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXPORT = ROOT / 'EECBench/exports/eecbench_first200_multimodel_20260926'
QUEUE = ROOT / 'EECBench/experiments/wan_generation_400_20260921/prompt_revision_20260922/input_queue_400.v2.jsonl'
MODELS = [
    ('wan21', 'Wan2.1-T2V-1.3B', 'hf_dataset', 'shot'),
    ('cinetrans', 'CineTrans-DiT', 'hf_dataset', 'episode'),
    ('wan22', 'Wan2.2-T2V-A14B', 'local_generation_run', 'shot'),
    ('storymem', 'StoryMem', None, 'shot'),
    ('holocine', 'HoloCine', 'local_accepted', 'episode'),
]


def load_json(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write_jsonl(path, rows):
    with Path(path).open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(f'Batch output already exists: {out}')

    queue_rows = [json.loads(line) for line in QUEUE.read_text().splitlines() if line.strip()]
    selected = sorted(queue_rows, key=lambda row: row['generation_priority'])[:200]
    if len(selected) != 200 or [r['generation_priority'] for r in selected] != list(range(1, 201)):
        raise ValueError('The first 200 source queue priorities are not a complete 1..200 sequence')

    video_index = [json.loads(line) for line in (EXPORT / 'video_index.jsonl').read_text().splitlines() if line.strip()]
    tasks = []
    episode_rows = []
    for queue in selected:
        eid = queue['episode_id']
        ep_dir = EXPORT / 'episodes' / eid
        metadata = load_json(ep_dir / 'episode.json')
        canonical = load_json(ep_dir / 'prompts/canonical_queue_record.json')
        contract = (ep_dir / 'source/contract.json').resolve()
        if metadata['episode_id'] != eid or canonical['episode_id'] != eid:
            raise ValueError(f'Episode ID mismatch for {eid}')
        if metadata['generation_priority'] != queue['generation_priority']:
            raise ValueError(f'Priority mismatch for {eid}')
        if len(canonical['shots']) != metadata['shot_count']:
            raise ValueError(f'Shot count mismatch for {eid}')
        if not contract.is_file() or load_json(contract).get('episode_id') != eid:
            raise ValueError(f'Missing or mismatched source contract for {eid}')

        episode_rows.append(dict(generation_priority=queue['generation_priority'], episode_id=eid,
                                 shot_count=metadata['shot_count'], target_duration_seconds=metadata['target_duration_seconds']))
        for model_id, model_name, variant, scope in MODELS:
            if model_id == 'storymem':
                storymem_variants = [v for v in metadata['models'][model_name].get('variants', [])
                                     if v.get('status') == 'complete'
                                     and v.get('source', {}).get('repository_or_run') == 'BlueSourceJY/ERCBench-StoryMem-400']
                if len(storymem_variants) != 1:
                    raise ValueError(f'{eid}/StoryMem: expected one complete Hub variant, got {len(storymem_variants)}')
                variant = storymem_variants[0]['variant']
            matches = [row for row in video_index
                       if row.get('episode_id') == eid and row.get('model') == model_name
                       and row.get('variant') == variant and row.get('status') == 'complete'
                       and row.get('scope') == scope]
            if scope == 'shot':
                matches.sort(key=lambda row: row.get('shot_id', ''))
                if len(matches) != metadata['shot_count']:
                    raise ValueError(f'{eid}/{model_name}: expected {metadata["shot_count"]} complete shot videos, got {len(matches)}')
            elif len(matches) != 1:
                raise ValueError(f'{eid}/{model_name}: expected one complete episode video, got {len(matches)}')

            shot_specs = []
            cumulative = 0.0
            for index, shot in enumerate(canonical['shots']):
                item = matches[index] if scope == 'shot' else matches[0]
                source = (EXPORT / item['path']).resolve()
                if not source.is_file() or source.stat().st_size != item['bytes']:
                    raise ValueError(f'Video missing or size mismatch: {source}')
                duration = float(shot['target_duration_seconds'])
                shot_specs.append(dict(
                    shot_id=shot['shot_id'], target_duration_seconds=duration,
                    source_scope=scope, source_shot_id=item.get('shot_id'),
                    source_video=str(source), source_bytes=item['bytes'],
                    source= item.get('source', {}),
                    episode_offset_sec=round(cumulative, 9) if scope == 'episode' else None,
                ))
                cumulative += duration

            variant_meta = next((v for v in metadata['models'][model_name].get('variants', [])
                                 if v.get('variant') == variant), {})
            prompt_paths = []
            for prompt in variant_meta.get('artifacts', {}).get('prompts', []):
                path = (EXPORT / prompt['path']).resolve()
                if path.is_file():
                    prompt_paths.append(dict(label=prompt.get('label'), path=str(path), sha256=sha(path)))
            tasks.append(dict(
                task_id=f'priority_{queue["generation_priority"]:03d}__{model_id}',
                generation_priority=queue['generation_priority'], episode_id=eid,
                model_id=model_id, model_name=model_name, variant=variant,
                source_scope=scope, shot_count=metadata['shot_count'],
                total_target_duration_seconds=round(cumulative, 9),
                contract_path=str(contract), contract_sha256=sha(contract),
                canonical_prompt_path=str((ep_dir / 'prompts/canonical_queue_record.json').resolve()),
                canonical_prompt_sha256=sha(ep_dir / 'prompts/canonical_queue_record.json'),
                model_prompt_artifacts=prompt_paths,
                source_metadata_path=str((ep_dir / 'episode.json').resolve()),
                shots=shot_specs,
            ))

    tasks.sort(key=lambda task: (task['generation_priority'], [m[0] for m in MODELS].index(task['model_id'])))
    if len(tasks) != 1000:
        raise ValueError(f'Expected 1000 model/episode tasks, got {len(tasks)}')
    out.mkdir(parents=True)
    write_jsonl(out / 'worklist.jsonl', tasks)
    write_jsonl(out / 'episodes.jsonl', episode_rows)
    (out / 'cohort.json').write_text(json.dumps(dict(
        protocol='vl_vv_first200_multimodel_v1', status='manifest_frozen',
        episode_count=200, task_count=1000,
        episode_order='ascending source generation_priority (1..200)',
        model_order=[m[1] for m in MODELS],
        model_variants={m[1]: sorted({t['variant'] for t in tasks if t['model_name'] == m[1]}) for m in MODELS},
        source_queue=str(QUEUE), source_queue_sha256=sha(QUEUE),
        source_export=str(EXPORT), export_verification=load_json(EXPORT / 'verification.json'),
        created_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    ), ensure_ascii=False, indent=2) + '\n')
    print(f'Wrote {len(tasks)} tasks for {len(episode_rows)} ordered episodes: {out}')


if __name__ == '__main__':
    main()
