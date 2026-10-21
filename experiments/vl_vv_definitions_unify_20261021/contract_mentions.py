#!/usr/bin/env python3
"""Keyword count: worn/carried items named only inside a character description of the first-200
contracts (no own entity entry). Approximate (English keyword matching). -> contract_mentions.json"""
import collections, glob, json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ACCESSORY = ['wristwatch', 'watch', 'sunglasses', 'glasses', 'spectacles', 'earring', 'ear stud', 'necklace', 'bracelet',
             'ring', 'hat', 'cap', 'beanie', 'helmet', 'scarf', 'backpack', 'handbag', 'purse', 'bag', 'tie', 'belt', 'gloves',
             'headphones', 'headband', 'mask', 'badge', 'lanyard', 'apron', 'phone', 'cigarette', 'microphone', 'umbrella']
GARMENT = ['shirt', 't-shirt', 'jacket', 'coat', 'dress', 'sweater', 'hoodie', 'trousers', 'pants', 'jeans', 'skirt', 'shorts',
           'blouse', 'vest', 'suit', 'robe', 'uniform', 'boots', 'shoes', 'sneakers']

def hits(text, words):
    t, out = text.lower(), set()
    for w in sorted(words, key=len, reverse=True):
        if re.search(r'(?<![a-z-])' + re.escape(w) + r's?(?![a-z])', t) and not any(w in o for o in out):
            out.add(w)
    return out

seen = {}
for f in sorted(glob.glob(str(EXP / 'vl_vv_multimodel_first200_run02*/wan21/priority_*/attempt_01/work/case/contract.json'))):
    seen.setdefault(re.search(r'priority_(\d+)', f).group(1), f)
episodes, nested_counter, own, garments, garment_eps, sizes = {}, collections.Counter(), 0, 0, 0, []
for p, f in seen.items():
    ents = json.load(open(f))['entity_descriptions']; sizes.append(len(ents))
    names = {k: (v.get('name') or '').lower() for k, v in ents.items()}
    nested, g = [], 0
    for k, v in ents.items():
        if not k.startswith('Character'):
            continue
        for w in sorted(hits(v.get('description', ''), ACCESSORY)):
            if any(w in names[o] for o in ents if o != k):
                own += 1
            else:
                nested.append([k, w])
        g += len(hits(v.get('description', ''), GARMENT))
    if nested:
        episodes[p] = nested; nested_counter.update(w for _, w in nested)
    garments += g; garment_eps += bool(g)
out = dict(contracts=len(seen), episodes_with_nested_items=len(episodes), nested_mentions=sum(map(len, episodes.values())),
           most_common=nested_counter.most_common(15), items_with_own_entry=own, garment_mentions=garments,
           episodes_with_garments=garment_eps, entities_per_contract_mean=round(sum(sizes) / len(sizes), 1),
           entities_per_contract_max=max(sizes), per_episode=episodes)
json.dump(out, open(HERE / 'contract_mentions.json', 'w'), indent=1)
print({k: v for k, v in out.items() if k != 'per_episode'})
