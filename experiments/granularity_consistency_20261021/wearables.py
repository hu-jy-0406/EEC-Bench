#!/usr/bin/env python3
"""Granularity consistency for worn items (garments + accessories): EntityBench vs our Full400 contracts.

A worn-item word (e.g. "glasses") is
  promoted - it occurs in an Object entry's name;
  nested   - it occurs in a Character description but in no Object name of that episode.
Measures (approximate, English keyword matching):
  per word across episodes: episodes where it is promoted vs nested-only;
  episodes mixing promoted and nested-only worn items;
  characters with both promoted and nested worn items;
  promoted items also named in a character description (the same item stored twice).
EntityBench only: schedule coverage of promoted worn items relative to the character they co-occur with most.
-> wearables.json
"""
import collections, glob, json, re, statistics
from pathlib import Path
HERE = Path(__file__).resolve().parent
EB = HERE.parents[2] / 'EntityBench/data/scripts'
OURS = HERE.parent / 'episode_contracts_20260921/deliverables/episodes'
WORDS = ['wristwatch', 'watch', 'sunglasses', 'glasses', 'earring', 'necklace', 'bracelet', 'ring', 'hat', 'cap', 'beanie',
         'helmet', 'scarf', 'tie', 'belt', 'gloves', 'headband', 'mask', 'badge', 'apron', 'backpack', 'bag',
         'shirt', 't-shirt', 'jacket', 'coat', 'dress', 'gown', 'sweater', 'hoodie', 'trousers', 'pants', 'jeans', 'skirt',
         'vest', 'suit', 'robe', 'uniform', 'boots', 'shoes', 'sweatshirt', 'tracksuit', 'blazer', 'cardigan']

def words_in(text):
    t, out = text.lower(), set()
    for w in sorted(WORDS, key=len, reverse=True):
        if re.search(r'(?<![a-z-])' + re.escape(w) + r's?(?![a-z])', t) and not any(w in o for o in out):
            out.add(w)
    return out

def analyse(episodes):
    per_word = {w: collections.Counter() for w in WORDS}
    mixed_eps = eps_with_any = 0; chars_mixed = chars_with_2 = 0; promoted = dual = 0
    for ents in episodes:
        objs = [v for k, v in ents.items() if k.startswith('Object')]
        chars = [v for k, v in ents.items() if k.startswith('Character')]
        obj_words = set().union(*[words_in(o['name']) for o in objs]) if objs else set()
        char_words = set().union(*[words_in(c.get('description', '')) for c in chars]) if chars else set()
        nested = char_words - obj_words
        for w in obj_words: per_word[w]['promoted'] += 1
        for w in nested: per_word[w]['nested_only'] += 1
        if obj_words or nested:
            eps_with_any += 1
            mixed_eps += bool(obj_words and nested)
        for c in chars:
            ws = words_in(c.get('description', ''))
            if len(ws) >= 2:
                chars_with_2 += 1
                chars_mixed += bool(ws & obj_words and ws - obj_words)
        for o in objs:
            ws = words_in(o['name'])
            if ws:
                promoted += 1
                dual += bool(ws & char_words)
    table = sorted(((w, c['promoted'], c['nested_only']) for w, c in per_word.items() if c['promoted'] and c['nested_only']),
                   key=lambda r: -(r[1] + r[2]))
    return dict(episodes=len(episodes), episodes_with_worn_items=eps_with_any, episodes_mixing_promoted_and_nested=mixed_eps,
                characters_with_2plus_worn_items=chars_with_2, of_which_mixed=chars_mixed,
                promoted_worn_objects=promoted, promoted_also_in_a_character_description=dual,
                words_both_ways=[dict(word=w, promoted_in=p, nested_only_in=n) for w, p, n in table[:16]])

eb_eps, coverage = [], []
for f in sorted(EB.glob('*.json')):
    d = json.load(open(f)); ents = d['entity_descriptions']; eb_eps.append(ents)
    sched = d['entity_schedule']
    for o in (v for k, v in ents.items() if k.startswith('Object') and words_in(v['name'])):
        shots = [k for k, s in sched.items() if o['name'] in s.get('objects', [])]
        if not shots: continue
        co = collections.Counter(c for k in shots for c in sched[k].get('characters', []))
        if not co: continue
        wearer, _ = co.most_common(1)[0]
        wearer_shots = [k for k, s in sched.items() if wearer in s.get('characters', [])]
        coverage.append(len(set(shots) & set(wearer_shots)) / len(wearer_shots))
ours_eps = [json.load(open(f))['entity_descriptions'] for f in sorted(OURS.glob('*/contract.json'))]
out = dict(entitybench=analyse(eb_eps), ours=analyse(ours_eps),
           entitybench_promoted_item_schedule_coverage=dict(
               items=len(coverage), median=round(statistics.median(coverage), 3),
               share_scheduled_in_all_wearer_shots=round(sum(c >= 0.999 for c in coverage) / len(coverage), 3),
               share_below_half=round(sum(c < 0.5 for c in coverage) / len(coverage), 3)))
json.dump(out, open(HERE / 'wearables.json', 'w'), indent=1)
for k in ('entitybench', 'ours'):
    r = out[k]; print('==', k, {kk: vv for kk, vv in r.items() if kk != 'words_both_ways'})
    print('   words promoted in some episodes, nested-only in others:', [(x['word'], x['promoted_in'], x['nested_only_in']) for x in r['words_both_ways'][:12]])
print('== EntityBench promoted worn items, share of the co-occurring character\'s shots where the item is scheduled:', out['entitybench_promoted_item_schedule_coverage'])
