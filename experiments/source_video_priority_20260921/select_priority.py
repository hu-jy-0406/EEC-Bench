#!/usr/bin/env python3
"""Frozen pre-generation, text/metadata-only selection. No prompt rewriting.

Small stdlib-only min-cost flows maximize documented surrogate scores within
source x length x style quotas and source-work caps. Scores are NOT probabilities
of generating unbound objects or calibrated measures of benchmark difficulty.
"""
import collections
import csv
import hashlib
import heapq
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / 'EECBench/experiments/source_video_400_20260920/deliverables/candidates_400.jsonl'
VERSION = 'priority_v1_text_metadata_20260921'
STYLES = ['live_action_narrative', 'animation', 'documentary']
# Closely rounded style margins, preserving EXACT source x shot-count margins.
# Each tuple is live action / animation / documentary.
CORE_QUOTAS = {('muss', 4): (27, 2, 1), ('muss', 6): (14, 1, 0),
               ('muss', 8): (5, 0, 0), ('sf20k', 4): (23, 6, 1),
               ('sf20k', 6): (13, 2, 0), ('sf20k', 8): (4, 1, 0)}
PRIORITY_QUOTAS = {('muss', 4): (54, 5, 1), ('muss', 6): (28, 2, 0),
                   ('muss', 8): (9, 1, 0), ('sf20k', 4): (47, 11, 2),
                   ('sf20k', 6): (26, 4, 0), ('sf20k', 8): (9, 1, 0)}

# Setting labels are SOURCE metadata, not additional generation requirements.
# Richness denotes plausible incidental-object opportunities; listed objects in
# the actual prompt remain bound. No absent-ID => unbound shortcut is used.
SETTINGS = [
    ('retail_dining', 1.0, r'\b(shop|store|restaurant|diner|café|cafe|bar|pub|market|hardware|dining|kitchen|kitchenette)\b'),
    ('work_public', .95, r'\b(office|library|desk|reception|waiting|studio|worktable|workstation|draft|classroom|laboratory|botanical|conference|hospital)\b'),
    ('domestic', .9, r'\b(bedroom|bedside|living|parlor|vanity|furnished|sofa|bed|domestic|bathroom|washroom)\b|\b(sitting|communal) (room|area)\b'),
    ('industrial_performance', .8, r'\b(industrial|equipment|workshop|storage|machinery|arcade|performance|stage|casino|venue|training|courtroom)\b'),
    ('built_outdoor', .7, r'\b(street|courtyard|yard|rooftop|garden|pier|porch|terrace|alley|sidewalk|settlement|forecourt|storefront|building|railway|campsite|shelter|counter|garage)\b'),
    ('vehicle_enclosure', .4, r'\b(car|vehicle|elevator|pod|pods|aircraft|cockpit|compartment|train|transport|enclosure)\b|\b(occupied|front|passenger|van) cabin\b'),
    ('generic_interior', .55, r'\b(room|interior|hall|hallway|corridor|doorway|landing|stairwell|window|mirror|paneled|table)\b'),
    ('natural_outdoor', .3, r'\b(forest|woodland|wooded|clearing|tree|trees|waterfront|lakeshore|riverbank|field|beach|dune|dunes|desert|ridge|mountain|rocky|cliff|plain|pool|ice|gorge|cavern|scrub|hillside|coast|water)\b'),
]
CONTEXT = re.compile(r'\b(wide|wider|medium|waist[- ]up|full[- ]body|two[- ]shot|establishing)\b|over[- ](?:the[- ])?shoulder', re.I)
DETAIL = re.compile(r'\b(close[- ]?up|close view|closer view|chest[- ]up|tight|macro|face fills)\b', re.I)
VIEW = re.compile(r'\b(reverse|overhead|low[- ]angle|high[- ]angle|side view|rear view|frontal|oblique|wide|medium)\b|over[- ](?:the[- ])?shoulder', re.I)
LAYOUT = re.compile(r'\b(table|desk|chair|sofa|shelf|shelves|cabinet|counter|lamp|doorway|window|railing|bench|bed|reel|reels|furniture)\b', re.I)
ACTION_RISK = re.compile(r'\b(explosion|explodes|gunfire|shootout|battle|fight|fighting|struggle|chase|attacks|tentacles|transforms|transformation)\b', re.I)
VIRTUAL = re.compile(r'\b(pixel[- ]art|sprite|sprites|gameplay|video game|television images)\b', re.I)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def features(row, index):
    n = row['shot_count']
    scenes = row['scenes']
    confirmed = [s for s in scenes if s.get('certainty') == 'confirmed']
    pairs = sum(max(0, len(s['shot_ids']) - 1) for s in confirmed)
    dominant = max((len(s['shot_ids']) for s in confirmed), default=0) / n
    confirmed_fraction = sum(len(s['shot_ids']) for s in confirmed) / n
    texts = [s['generation_prompt_en'] for s in row['shots']]
    context = sum(bool(CONTEXT.search(t)) for t in texts) / n
    # Actual prompt framing is scored; observed source camera is diagnostic only.
    source_context = sum(bool(CONTEXT.search(s.get('observed_camera', ''))) for s in row['shots']) / n
    close = sum(bool(DETAIL.search(t)) and not CONTEXT.search(t) for t in texts) / n
    layout = sum(bool(LAYOUT.search(t)) for t in texts) / n
    views = sorted({m.group(0).lower() for t in texts for m in VIEW.finditer(t)})
    families = collections.Counter()
    richness = 0
    setting_evidence = []
    for scene in scenes:
        family, strength, hit = 'other', .2, None
        for name, value, pattern in SETTINGS:
            m = re.search(pattern, scene['label'], re.I)
            if m:
                family, strength, hit = name, value, m.group(0)
                break
        weight = len(scene['shot_ids']) / n
        families[family] += len(scene['shot_ids'])
        richness += weight * strength
        setting_evidence.append({'scene_id': scene['scene_id'], 'label': scene['label'],
                                 'family': family, 'matched_word': hit, 'strength': strength})
    recurring = sum(any(len(set(s['shot_ids']) & {o['shot_id'] for o in e['occurrences']}) >= 2
                        for s in confirmed) for e in row['entities'])
    common_counts = []
    shots = {s['shot_id']: s for s in row['shots']}
    order = {s['shot_id']: i for i, s in enumerate(row['shots'])}
    for scene in confirmed:
        ids = sorted(scene['shot_ids'], key=order.get)
        common_counts.extend(len(set(shots[a]['prompt_entity_ids']) & set(shots[b]['prompt_entity_ids']))
                             for a, b in zip(ids, ids[1:]))
    recurrence = .5 * min(recurring / 3, 1) + .5 * (sum(min(c / 2, 1) for c in common_counts) / len(common_counts) if common_counts else 0)
    motion_fraction = sum(bool(ACTION_RISK.search(t)) for t in texts) / n
    virtual_fraction = sum(bool(VIRTUAL.search(t)) for t in texts) / n
    # Spatial/appearance evidence needs room around actors, not only facial crops.
    scene_score = 35 * pairs / (n - 1) + 10 * dominant + 5 * confirmed_fraction
    opportunity_score = 20 * richness * (.4 + .6 * context)
    spatial_score = 8 * context + 4 * layout + 3 * min(len(views) / 3, 1)
    recurrence_score = 10 * recurrence
    quality_score = 5 * (1 - close)
    penalty = 6 * motion_fraction + 30 * virtual_fraction + (25 if virtual_fraction >= .5 else 0) + min(max(len(row['entities']) - 8, 0), 4)
    score = scene_score + opportunity_score + spatial_score + recurrence_score + quality_score - penalty
    return {
        'episode_id': row['episode_id'], 'source_index': index, 'source': row['source']['dataset'],
        'source_work_key': row['source_work_key'], 'source_type': row['source_type'],
        'shot_count': n, 'target_duration_seconds': row['target_duration_seconds'], 'title': row['title'],
        'priority_score': round(score, 8), 'confirmed_same_scene_transitions': pairs,
        'same_scene_transition_fraction': pairs / (n - 1), 'dominant_confirmed_scene_fraction': dominant,
        'single_confirmed_scene': len(scenes) == 1 and len(confirmed) == 1,
        'confirmed_scene_shot_fraction': confirmed_fraction,
        'prompt_context_framing_fraction': context, 'source_context_framing_fraction': source_context,
        'close_only_fraction': close, 'layout_prompt_fraction': layout,
        'setting_richness_proxy': richness, 'dominant_setting_family': families.most_common(1)[0][0],
        'setting_evidence': setting_evidence, 'view_cues': views,
        'recurring_source_entities': recurring, 'adjacent_same_scene_prompt_id_intersections': common_counts,
        'action_risk_fraction': motion_fraction, 'virtual_content_fraction': virtual_fraction,
        'components': {'scene': scene_score, 'incidental_context_opportunity': opportunity_score,
                       'spatial_observability': spatial_score, 'identity_recurrence': recurrence_score,
                       'framing_quality': quality_score, 'penalty': penalty},
        'selection_basis': 'actual_prompt_text_and_source_metadata_only',
        'unbound_generation_probability': None,
    }


class Flow:
    def __init__(self):
        self.graph = collections.defaultdict(list)

    def edge(self, a, b, capacity, cost):
        f = [b, capacity, cost, len(self.graph[b])]
        r = [a, 0, -cost, len(self.graph[a])]
        self.graph[a].append(f)
        self.graph[b].append(r)
        return f

    def solve(self, start, finish, count):
        # Bellman-Ford once establishes potentials for negative score edges.
        dist = {v: float('inf') for v in self.graph}
        dist[start] = 0
        todo, queued = collections.deque([start]), {start}
        while todo:
            a = todo.popleft()
            queued.remove(a)
            for b, cap, cost, _ in self.graph[a]:
                if cap and dist[b] > dist[a] + cost:
                    dist[b] = dist[a] + cost
                    if b not in queued:
                        todo.append(b)
                        queued.add(b)
        potential = {v: (d if d < float('inf') else 0) for v, d in dist.items()}
        for _ in range(count):
            distance, prev, heap = {start: 0}, {}, [(0, start)]
            while heap:
                d, a = heapq.heappop(heap)
                if d != distance[a]:
                    continue
                for i, (b, cap, cost, _) in enumerate(self.graph[a]):
                    nd = d + cost + potential[a] - potential[b]
                    if cap and nd < distance.get(b, float('inf')):
                        distance[b], prev[b] = nd, (a, i)
                        heapq.heappush(heap, (nd, b))
            if finish not in prev:
                raise RuntimeError('Requested style/length/work constraints are infeasible; do not silently relax.')
            for v, d in distance.items():
                potential[v] += d
            b = finish
            while b != start:
                a, i = prev[b]
                edge = self.graph[a][i]
                edge[1] -= 1
                self.graph[b][edge[3]][1] += 1
                b = a


def unpack(quotas):
    return {(s, n, t): values[i] for (s, n), values in quotas.items() for i, t in enumerate(STYLES)}


def select(pool, quotas, existing, work_cap):
    flow, edges = Flow(), {}
    existing_counts = collections.Counter(r['source_work_key'] for r in existing)
    for work in sorted({r['source_work_key'] for r in pool}):
        for occurrence in range(existing_counts[work], work_cap):
            # Prefer a new source work; second episode costs 8 ranking points.
            flow.edge('start', 'work:' + work, 1, occurrence * 8000 * 1000000)
    for i, r in enumerate(sorted(pool, key=lambda x: x['episode_id'])):
        key = (r['source'], r['shot_count'], r['source_type'])
        if not quotas.get(key):
            continue
        cost = -round(r['priority_score'] * 1000) * 1000000 + i
        edges[r['episode_id']] = flow.edge('work:' + r['source_work_key'], 'bucket:' + repr(key), 1, cost)
    for key, cap in sorted(quotas.items()):
        if cap:
            flow.edge('bucket:' + repr(key), 'finish', cap, 0)
    flow.solve('start', 'finish', sum(quotas.values()))
    chosen = {eid for eid, edge in edges.items() if edge[1] == 0}
    result = [r for r in pool if r['episode_id'] in chosen]
    assert len(result) == sum(quotas.values())
    return result


def interleave(stage):
    """Each 20-row block has 6/3/1 examples per source (12/6/2 overall)."""
    cells = collections.defaultdict(list)
    for r in stage:
        cells[r['source'], r['shot_count']].append(r)
    for rows in cells.values():
        rows.sort(key=lambda r: (-r['priority_score'], r['episode_id']))
    per_block = {(s, n): q for s in ['muss', 'sf20k'] for n, q in [(4, 6), (6, 3), (8, 1)]}
    result = []
    for block in range(len(stage) // 20):
        used = collections.Counter()
        for position in range(20):
            # Largest quota deficit first; score breaks equally due strata.
            eligible = [k for k in sorted(cells) if used[k] < per_block[k]]
            k = max(eligible, key=lambda k: ((position + 1) * per_block[k] / 20 - used[k],
                                             cells[k][0]['priority_score'], k))
            result.append(cells[k].pop(0))
            used[k] += 1
    assert all(not value for value in cells.values())
    return result


def statistics(rows):
    n = len(rows)
    works = collections.Counter(r['source_work_key'] for r in rows)
    return {'episodes': n, 'shots': sum(r['shot_count'] for r in rows),
            'duration_seconds': dict(sorted(collections.Counter(r['target_duration_seconds'] for r in rows).items())),
            'shot_counts': dict(sorted(collections.Counter(r['shot_count'] for r in rows).items())),
            'sources': dict(collections.Counter(r['source'] for r in rows)),
            'styles': dict(collections.Counter(r['source_type'] for r in rows)),
            'source_x_shots': {f'{s}/{k}': sum(r['source'] == s and r['shot_count'] == k for r in rows)
                               for s in ['muss', 'sf20k'] for k in [4, 6, 8]},
            'distinct_source_works': len(works), 'max_per_source_work': max(works.values()),
            'single_confirmed_scene_episodes': sum(r['single_confirmed_scene'] for r in rows),
            'mean_same_scene_transition_fraction': sum(r['same_scene_transition_fraction'] for r in rows) / n,
            'mean_prompt_context_framing_fraction': sum(r['prompt_context_framing_fraction'] for r in rows) / n,
            'mean_setting_richness_proxy': sum(r['setting_richness_proxy'] for r in rows) / n,
            'mean_priority_score': sum(r['priority_score'] for r in rows) / n,
            'setting_families': dict(collections.Counter(r['dominant_setting_family'] for r in rows))}


def main():
    data = SOURCE.read_bytes()
    lines = data.splitlines(keepends=True)
    records = [json.loads(line) for line in lines]
    assert len(records) == 400
    assert len({r['episode_id'] for r in records}) == 400
    original = {r['episode_id']: line for r, line in zip(records, lines)}
    record_map = {r['episode_id']: r for r in records}
    rows = [features(r, i) for i, r in enumerate(records)]
    for r in records:
        assert r['target_duration_seconds'] == 5 * r['shot_count']
        assert all(s['target_duration_seconds'] == 5 for s in r['shots'])
    q1, q2 = unpack(CORE_QUOTAS), unpack(PRIORITY_QUOTAS)
    first = select(rows, q1, [], 1)
    ids1 = {r['episode_id'] for r in first}
    second = select([r for r in rows if r['episode_id'] not in ids1],
                    {k: q2[k] - q1[k] for k in q2}, first, 2)
    ids2 = ids1 | {r['episode_id'] for r in second}
    third = [r for r in rows if r['episode_id'] not in ids2]
    first, second, third = map(interleave, [first, second, third])
    queue = first + second + third
    for i, r in enumerate(queue, 1):
        r.update(generation_rank=i, priority_stage=1 if i <= 100 else 2 if i <= 200 else 3,
                 balanced_block=(i - 1) // 20 + 1,
                 original_record_sha256=digest(original[r['episode_id']]))
    subsets = {'core_100': first, 'priority_200': first + second,
               'stage2_additional_100': second, 'stage3_remaining_200': third,
               'generation_queue_400': queue}
    outputs = {}
    for name, subset in subsets.items():
        raw = b''.join(original[r['episode_id']] for r in subset)
        (HERE / (name + '.jsonl')).write_bytes(raw)
        (HERE / (name + '.ids.txt')).write_text(''.join(r['episode_id'] + '\n' for r in subset))
        outputs[name] = {'path': str(HERE / (name + '.jsonl')), 'sha256': digest(raw),
                         'stats': statistics(subset)}
    (HERE / 'ranking.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in queue))
    columns = ['generation_rank', 'priority_stage', 'episode_id', 'title', 'source', 'source_work_key',
               'source_type', 'shot_count', 'target_duration_seconds', 'priority_score',
               'single_confirmed_scene', 'same_scene_transition_fraction', 'prompt_context_framing_fraction',
               'setting_richness_proxy', 'dominant_setting_family', 'recurring_source_entities',
               'action_risk_fraction', 'virtual_content_fraction']
    with (HERE / 'ranking.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(queue)
    checks = {'unique_400': len({r['episode_id'] for r in queue}) == 400,
              'core_is_exact_first100': queue[:100] == first,
              'priority_is_exact_first200': queue[:200] == first + second,
              'all_records_byte_preserved': all(original[r['episode_id']] == line for r, line in
                  zip(queue, (HERE / 'generation_queue_400.jsonl').read_bytes().splitlines(keepends=True))),
              'canonical_source_unchanged': digest(SOURCE.read_bytes()) == digest(data)}
    for name, subset in subsets.items():
        checks[name + '_strata_exact'] = all(
            outputs[name]['stats']['source_x_shots'][f'{s}/{k}'] == len(subset) * ratio
            for s in ['muss', 'sf20k'] for k, ratio in [(4, .3), (6, .15), (8, .05)])
    checks['every_20_row_block_balanced'] = all(
        collections.Counter((r['source'], r['shot_count']) for r in queue[i:i+20]) ==
        {(s, k): count for s in ['muss', 'sf20k'] for k, count in [(4, 6), (6, 3), (8, 1)]}
        for i in range(0, 400, 20))
    checks['core_max_one_per_work'] = statistics(first)['max_per_source_work'] == 1
    checks['priority_max_two_per_work'] = statistics(first + second)['max_per_source_work'] <= 2
    assert all(checks.values()), checks
    audit = {'version': VERSION, 'source': str(SOURCE), 'source_sha256': digest(data),
             'source_stats': statistics(rows), 'outputs': outputs, 'checks': checks,
             'model_calls': 0, 'model_tokens': 0, 'model_api_usd': 0,
             'human_video_review': False, 'generation_launched': False,
             'selection_uses_generated_model_outputs': False,
             'formal_schedules_required_for_queue': False}
    (HERE / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    (HERE / 'selection_manifest.json').write_text(json.dumps({
        'version': VERSION, 'source_sha256': digest(data), 'script_sha256': digest(Path(__file__).read_bytes()),
        'generation_order': ['core_100.jsonl', 'stage2_additional_100.jsonl', 'stage3_remaining_200.jsonl'],
        'cumulative_evaluation_sets': ['core_100.jsonl', 'priority_200.jsonl', 'generation_queue_400.jsonl'],
        'every_n_records_balanced': 20, 'all_models_share_identical_episode_order': True,
        'phase_barrier': 'Do not start stage 2 for a model until all its stage 1 episodes succeed or failures are explicitly recorded; likewise stage 3.',
        'cross_model_policy': 'Under deadline, prioritize finishing core100 on ALL three models before allocating optional expansion capacity.',
        'completion_warning': 'Dispatch order alone does not guarantee a balanced completed sample; complete/retry all episodes in a reported subset.',
        'resume_key': ['model_id', 'episode_id', 'model_config_hash', 'adapted_prompt_hash', 'seed'],
        'record_hashes': {r['episode_id']: r['original_record_sha256'] for r in queue},
        'quota_core': {str(k): v for k, v in CORE_QUOTAS.items()},
        'quota_cumulative200': {str(k): v for k, v in PRIORITY_QUOTAS.items()},
        'scoring_weights': {'same_scene': 50, 'incidental_context_opportunity_proxy': 20,
                            'spatial_observability': 15, 'identity_recurrence': 10, 'framing_quality': 5},
        'diversity_penalty_second_work_occurrence': 8,
        'model_specific_adapters': 'Required separately; preserve complete prompt semantics and use identical selected IDs. Source schedule compilation may run concurrently.',
        'human_review_flags_unchanged': True, 'files': outputs,
    }, ensure_ascii=False, indent=2) + '\n')
    e = html.escape
    cards = []
    for r in queue:
        x = record_map[r['episode_id']]
        shots = ''.join('<p><b>' + e(s['shot_id']) + '</b> ' + e(s['generation_prompt_en']) + '</p>' for s in x['shots'])
        clip = x.get('source_clip', {}).get('path', '')
        cards.append(f'<details data-stage="{r["priority_stage"]}"><summary>#{r["generation_rank"]} · Stage {r["priority_stage"]} · {r["shot_count"]} shots / {r["target_duration_seconds"]}s · {e(r["title"])}</summary><p>{e(r["episode_id"])} · {e(r["source"])} · score {r["priority_score"]:.2f}</p><p>Confirmed same-scene transitions: {r["confirmed_same_scene_transitions"]}/{r["shot_count"]-1}; setting: {e(r["dominant_setting_family"])}</p><p><a href="{e(clip)}">Original source clip</a></p><p><b>Global:</b> {e(x["global_prompt"])}</p>{shots}</details>')
    (HERE / 'review.html').write_text('<!doctype html><meta charset="utf-8"><title>EEC priority subsets</title><style>body{max-width:1100px;margin:30px auto;font:16px/1.6 sans-serif;background:#f8fafc;color:#172b4d}details{padding:12px;margin:8px 0;background:white;border:1px solid #cbd5e1}summary{cursor:pointer}button{margin:6px;padding:8px}</style><h1>EEC 100 ⊂ 200 ⊂ 400</h1><p>Original prompts preserved. Text/metadata selection; unbound opportunity is a proxy, not an observed outcome. No human video review claimed.</p><button onclick="filter(1)">Core 100</button><button onclick="filter(2)">Cumulative 200</button><button onclick="filter(3)">All 400</button>' + ''.join(cards) + '<script>function filter(n){document.querySelectorAll("details").forEach(x=>x.hidden=Number(x.dataset.stage)>n)}filter(1)</script>')
    print(json.dumps({'checks': checks, 'source': audit['source_stats'],
                      'subsets': {k: v['stats'] for k, v in outputs.items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
