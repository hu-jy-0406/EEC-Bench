#!/usr/bin/env python3
"""Confirmed V-V issues of the C + plug-in run by subcategory and scope, and by whether a subject is unspecified.
Within the clothing/accessory subcategories, which item the description names (first matching keyword group).
Zero model calls. Writes issue_subcategories.json."""
import collections
import json
import re
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / 'vl_vv_full_first200_c_20261110' / 'runs'
ITEMS = [
    ('trousers', r'裤|pants|trousers|jeans'), ('footwear', r'鞋|靴|shoe|boot'),
    ('eyewear', r'眼镜|墨镜|太阳镜|glasses'), ('headwear', r'帽|头盔|头巾|发夹|发饰|发带|hat\b|cap\b|helmet'),
    ('tie_scarf', r'领带|领结|围巾|丝巾|\btie\b|scarf'),
    ('jewelry_watch', r'项链|耳环|耳钉|手镯|手链|戒指|手表|腕表|胸针|吊坠|necklace|earring|bracelet|watch|brooch'),
    ('badge_strap_belt', r'挂绳|工牌|胸牌|徽章|名牌|腰带|皮带|背带|lanyard|badge|belt'),
    ('bag', r'背包|手提包|挎包|公文包|书包|钱包|手包|bag\b|backpack|purse'),
    ('gloves_apron', r'手套|围裙|glove|apron'),
    ('hair_beard', r'发型|头发|发色|发髻|刘海|卷发|直发|短发|长发|胡须|胡子|hair|beard'),
    ('clothing', r'衬衫|上衣|外套|夹克|西装|毛衣|连衣裙|裙|T恤|卫衣|大衣|背心|制服|衣领|领口|袖|衣服|服装|着装|开衫|shirt|jacket|coat|dress|sweater|suit|uniform|clothing|outfit'),
]
RX = [(k, re.compile(v, re.I)) for k, v in ITEMS]
sub = collections.defaultdict(collections.Counter)
items = collections.defaultdict(collections.Counter)
ex = collections.defaultdict(list)
for base in sorted(RUNS.iterdir()):
    r = json.loads((base / 'results_with/vv_review/result.json').read_text())
    lab = {e['entity_key']: e.get('label') for e in r.get('entities') or []}
    name = {e['entity_key']: e.get('name') for e in r.get('entities') or []}
    for u in r['units']:
        if u['verdict'] != 'confirmed':
            continue
        subs = [x['entity_key'] for x in u.get('entity_refs') or [] if x.get('role') == 'subject']
        uns = any(lab.get(s) == 'unspecified' for s in subs)
        key = f"{u['scope']}:{u['subcategory']}"
        sub[key]['unspecified' if uns else 'specified'] += 1
        if len(ex[key]) < 3 and not uns:
            ex[key].append(f"{base.name} {[name.get(s) for s in subs]} {(u.get('description') or '')[:120]}")
        if u['subcategory'] in ('character_appearance', 'appearance_drift'):
            text = u.get('description') or ''
            hit = [k for k, rx in RX if rx.search(text)]
            items[key]['issues'] += 1
            for k in hit:  # every item group the description names (multi-label)
                items[key][k] += 1
            if not hit:
                items[key]['none'] += 1
out = dict(subcategories={k: dict(v) for k, v in sorted(sub.items(), key=lambda kv: -sum(kv[1].values()))},
           clothing_items={k: dict(v.most_common()) for k, v in items.items()}, examples=ex)
Path(__file__).with_name('issue_subcategories.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
for k, v in out['subcategories'].items():
    print(f"{k:45} spec {v.get('specified', 0):4} unspec {v.get('unspecified', 0):3}")
print(json.dumps(out['clothing_items'], ensure_ascii=False, indent=1))
