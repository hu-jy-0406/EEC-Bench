#!/usr/bin/env python3
"""Compile the requirement package (requirements.json, prompt_registry.json, narrative.json) of each episode.

Default: the 400 episodes of experiments/source_video_priority_20260921/generation_queue_400.ids.txt, each from
its current contract with evidence (episode_contract.resolve_v2_contract).  Re-running with an unchanged
contract leaves the files identical; a package whose contract changed needs --update.  No model or API calls.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import episode_contract as contract_io  # noqa: E402
import episode_requirements as compiler  # noqa: E402

IDS = ROOT / 'experiments/source_video_priority_20260921/generation_queue_400.ids.txt'


def compile_all(ids, out_root, update=False):
    out_root = Path(out_root)
    records = []
    for episode_id in ids:
        contract_path = contract_io.resolve_v2_contract(episode_id)
        folder = out_root / episode_id
        existing = folder / compiler.FILE
        status = 'new'
        if existing.is_file():
            old = json.loads(existing.read_text())
            changed = old['source_contract_sha256'] != compiler.file_sha(contract_path)
            if changed and not update:
                raise ValueError(f'{episode_id}: contract changed since compilation ({old["source_contract"]} -> '
                                 f'{contract_path}); use --update to recompile')
            status = 'updated' if changed else 'unchanged'
        package = compiler.compile_episode(contract_path)
        if status == 'unchanged':
            # Same contract: keep the stored compiler record so files stay identical across compiler edits.
            package[compiler.FILE]['compiler'] = old['compiler']
        compiler.write_package(folder, package)
        req = package[compiler.FILE]
        records.append(dict(episode_id=episode_id, status=status, source_contract=req['source_contract'],
                            source_contract_sha256=req['source_contract_sha256'],
                            model_contract_sha256=req['model_contract_sha256'],
                            requirements_sha256=compiler.file_sha(folder / compiler.FILE),
                            prompt_registry_sha256=req['prompt_registry_sha256'], narrative_sha256=req['narrative_sha256'],
                            requirement_count=len(req['requirements'])))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episodes', nargs='*', help='Episode IDs (default: the 400-episode queue)')
    parser.add_argument('--ids-file', type=Path, default=IDS)
    parser.add_argument('--output', type=Path, default=contract_io.COMPILED_ROOT)
    parser.add_argument('--update', action='store_true', help='Recompile packages whose contract changed')
    args = parser.parse_args()
    ids = args.episodes or [line.strip() for line in args.ids_file.read_text().splitlines() if line.strip()]
    records = compile_all(ids, args.output, args.update)
    index = args.output / 'index.jsonl'
    old = {}
    if index.is_file():
        old = {row['episode_id']: row for row in map(json.loads, index.read_text().splitlines() if index.read_text() else [])}
    for row in records:
        old[row['episode_id']] = {key: value for key, value in row.items() if key != 'status'}
    index.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in old.values()))
    counts = {}
    for row in records:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    print(json.dumps(dict(episodes=len(records), **counts, index=str(index))))


if __name__ == '__main__':
    main()
