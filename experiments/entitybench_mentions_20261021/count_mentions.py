#!/usr/bin/env python3
"""How EntityBench (140 released episodes) represents entities mentioned in prompts.

Counts (approximate, English keyword/name matching):
  A. worn/carried items named only inside a character description (same keyword list and rule as
     experiments/vl_vv_definitions_unify_20261021/contract_mentions.py for our contracts);
  B. objects whose registry entry is itself a garment/accessory (an item promoted to an entity) and
     whether a character description also names it;
  C. registry entities named in a shot's action text but not scheduled in that shot;
  D. scheduled names with no registry description.
Output: entitybench_mentions.json and a random sample of shots for manual reading (sample_shots.json).
"""
import collections, glob, json, random, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / 'EntityBench/data/scripts'
ACCESSORY = ['wristwatch', 'watch', 'sunglasses', 'glasses', 'spectacles', 'earring', 'ear stud', 'necklace', 'bracelet',
             'ring', 'hat', 'cap', 'beanie', 'helmet', 'scarf', 'backpack', 'handbag', 'purse', 'bag', 'tie', 'belt', 'gloves',
             'headphones', 'headband', 'mask', 'badge', 'lanyard', 'apron', 'phone', 'cigarette', 'microphone', 'umbrella']
GARMENT = ['shirt', 't-shirt', 'jacket', 'coat', 'dress', 'sweater', 'hoodie', 'trousers', 'pants', 'jeans', 'skirt', 'shorts',
           'blouse', 'vest', 'suit', 'robe', 'uniform', 'boots', 'shoes', 'sneakers', 'tracksuit', 'sweatshirt', 'blazer']

def hits(text, words):
    t, out = text.lower(), set()
    for w in sorted(words, key=len, reverse=True):
        if re.search(r'(?<![a-z-])' + re.escape(w) + r's?(?![a-z])', t) and not any(w in o for o in out):
            out.add(w)
    return out

def mentioned(name, text):
    core = re.sub(r'^(the|a|an)\s+', '', name.lower()).strip()
    return bool(core) and re.search(r'(?<![a-z0-9])' + re.escape(core) + r'(?![a-z0-9])', text.lower()) is not None

episodes = sorted(SCRIPTS.glob('*.json'))
A_eps, A_total, A_counter, A_own = 0, 0, collections.Counter(), 0
B_items, B_dual = [], 0
C_shots, C_total, C_examples, shots_total = 0, 0, [], 0
D_total, D_examples, sched_total = 0, [], 0
sizes, sample_pool = [], []
for path in episodes:
    d = json.load(open(path)); ents = d['entity_descriptions']; sizes.append(len(ents))
    names = {k: v['name'] for k, v in ents.items()}
    lower_names = {k: v.lower() for k, v in names.items()}
    char_text = ' '.join(v['description'] for k, v in ents.items() if k.startswith('Character'))
    nested = []
    for k, v in ents.items():
        if not k.startswith('Character'):
            continue
        for w in sorted(hits(v['description'], ACCESSORY)):
            if any(w in lower_names[o] for o in ents if o != k):
                A_own += 1
            else:
                nested.append(w)
    if nested:
        A_eps += 1; A_total += len(nested); A_counter.update(nested)
    for k, v in ents.items():
        if k.startswith('Object') and hits(v['name'], GARMENT + ACCESSORY):
            dual = bool(hits(v['name'], GARMENT + ACCESSORY) & hits(char_text, GARMENT + ACCESSORY))
            B_items.append(dict(episode=path.stem[:40], object=v['name'], also_in_character_description=dual)); B_dual += dual
    for sc in d['scenes']:
        for i, action in enumerate(sc['action_descriptions']):
            key = f"{sc['scene_num']}:{i + 1}"; shots_total += 1
            sched = d['entity_schedule'].get(key, {})
            scheduled = set(sched.get('characters', []) + sched.get('places', []) + sched.get('objects', []))
            sched_total += len(scheduled)
            missing = [n for n in names.values() if n not in scheduled and mentioned(n, action)]
            if missing:
                C_shots += 1; C_total += len(missing)
                if len(C_examples) < 8: C_examples.append(dict(shot=f'{path.stem[:24]} {key}', unscheduled=missing, action=action[:220]))
            known = set(names.values())
            for n in scheduled - known:
                D_total += 1
                if len(D_examples) < 8: D_examples.append(dict(shot=f'{path.stem[:24]} {key}', name=n))
            sample_pool.append(dict(episode=path.name, shot=key, schedule=sched, action=action))
ours_shots = ours_gap = ours_mentions = 0
seen = {}
for f in sorted(glob.glob(str(HERE.parent / 'vl_vv_multimodel_first200_run02*/wan21/priority_*/attempt_01/work/case/contract.json'))):
    seen.setdefault(re.search(r'priority_(\d+)', f).group(1), f)
for f in seen.values():
    c = json.load(open(f)); our_names = {v['name'] for v in c['entity_descriptions'].values()}
    for s_ in c['prompt']['shots']:
        ours_shots += 1; sch = c['entity_schedule'].get(s_['schedule_key'], {})
        scheduled = set(sch.get('characters', []) + sch.get('places', []) + sch.get('objects', []))
        miss = [n for n in our_names if n not in scheduled and mentioned(n, s_['text'])]
        ours_gap += bool(miss); ours_mentions += len(miss)
random.seed(20261021)
sample = random.sample(sample_pool, 25)
out = dict(episodes=len(episodes), shots=shots_total, entities_per_episode_mean=round(sum(sizes) / len(sizes), 1),
           A_nested_items=dict(episodes=A_eps, mentions=A_total, most_common=A_counter.most_common(12), same_kind_with_own_entry=A_own),
           B_promoted_wearables=dict(objects=len(B_items), also_named_in_a_character_description=B_dual, examples=B_items[:12]),
           C_registry_entities_mentioned_but_unscheduled=dict(shots=C_shots, mentions=C_total, examples=C_examples),
           D_scheduled_without_registry_entry=dict(names=D_total, of_scheduled=sched_total, examples=D_examples),
           ours_registry_entities_mentioned_but_unscheduled=dict(shots=ours_gap, of_shots=ours_shots, mentions=ours_mentions),
           objects_total=sum(1 for f in episodes for k in json.load(open(f))['entity_descriptions'] if k.startswith('Object')))
json.dump(out, open(HERE / 'entitybench_mentions.json', 'w'), indent=1)
json.dump(sample, open(HERE / 'sample_shots.json', 'w'), indent=1)
print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != 'examples'}) for k, v in out.items()}, indent=1))
