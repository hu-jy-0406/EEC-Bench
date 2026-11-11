#!/usr/bin/env python3
"""Confirmed V-V issues of the C + plug-in run (1,000 videos) whose description mentions a category of thing that is
not an entity of its own today (worn items, body features, walls/floors, floor coverings, background vegetation and
sky, screen content and signage, reflections and depicted figures). Keyword matching on the issue description
(Chinese or English), so counts are approximate; a description can match several categories. For each category:
issues whose subjects are all specified (the item is folded into a person or place today, so the issue counts as
specified) and issues already counted unspecified. Zero model calls. Writes issue_categories.json."""
import collections
import json
import re
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / 'vl_vv_full_first200_c_20261110' / 'runs'
CATS = {
    'clothing_top': r'衬衫|上衣|外套|夹克|西装|毛衣|连衣裙|裙子|T恤|卫衣|大衣|背心|制服|衣领|领口|袖子|衣服|服装|着装|shirt|jacket|coat|dress|sweater|suit|blouse|uniform|sleeve|collar|outfit|clothing',
    'trousers': r'裤|pants|trousers|jeans',
    'footwear': r'鞋|靴|shoe|boot',
    'headwear': r'帽|头盔|头巾|发夹|发饰|发带|hat\b|cap\b|helmet|headband|hairpin',
    'eyewear': r'眼镜|墨镜|太阳镜|glasses|sunglasses|spectacles',
    'tie_scarf': r'领带|领结|围巾|丝巾|necktie|\btie\b|bow tie|scarf',
    'jewelry_watch': r'项链|耳环|耳钉|手镯|手链|戒指|手表|腕表|胸针|吊坠|necklace|earring|bracelet|wristwatch|\bwatch\b|brooch|pendant',
    'badge_belt_strap': r'挂绳|工牌|胸牌|徽章|名牌|腰带|皮带|背带|lanyard|badge|belt|strap',
    'bag_carried': r'背包|手提包|挎包|公文包|书包|钱包|手包|backpack|handbag|purse|briefcase|bag\b',
    'gloves_apron': r'手套|围裙|glove|apron',
    'hair_beard_makeup': r'发型|头发|发色|发髻|刘海|胡须|胡子|胡茬|妆|口红|hairstyle|hair\b|beard|mustache|makeup|lipstick',
    'wall_floor_ceiling': r'墙|地板|地面|天花板|瓷砖|wall|floor|ceiling|ground',
    'floor_covering': r'地毯|地垫|脚垫|rug|carpet|\bmat\b',
    'vegetation_sky': r'树|灌木|草地|草坪|天空|云|tree|bush|grass|lawn|sky|cloud',
    'screen_signage_text': r'屏幕|显示内容|显示屏|画面中的文字|文字|标志|招牌|标牌|字样|logo|screen|display|sign\b|signage|text',
    'reflection_depicted': r'倒影|镜中|镜子里|反射|映出|照片中|画中|海报上|reflection|mirror|portrait|poster',
    'pattern_print': r'图案|印花|条纹|格纹|pattern|print|stripe|plaid',
}
RX = {k: re.compile(v, re.I) for k, v in CATS.items()}
cnt = collections.defaultdict(collections.Counter)
examples = collections.defaultdict(list)
total = collections.Counter()
for base in sorted(RUNS.iterdir()):
    r = json.loads((base / 'results_with/vv_review/result.json').read_text())
    lab = {e['entity_key']: e.get('label') for e in r.get('entities') or []}
    name = {e['entity_key']: e.get('name') for e in r.get('entities') or []}
    for u in r['units']:
        if u['verdict'] != 'confirmed':
            continue
        subs = [x['entity_key'] for x in u.get('entity_refs') or [] if x.get('role') == 'subject']
        uns = any(lab.get(s) == 'unspecified' for s in subs)
        total['unspecified' if uns else 'specified'] += 1
        text = u.get('description') or ''
        for k, rx in RX.items():
            if rx.search(text):
                cnt[k]['unspecified' if uns else 'specified'] += 1
                cnt[k]['videos:' + base.name] = 1
                if not uns and len(examples[k]) < 6:
                    examples[k].append(dict(task=base.name, unit=u['unit_id'], subjects=[name.get(s) for s in subs], description=text[:160]))
out = dict(total_confirmed=dict(total), categories={k: dict(specified=v['specified'], unspecified=v['unspecified'],
           videos=sum(1 for x in v if x.startswith('videos:'))) for k, v in cnt.items()}, examples=examples)
Path(__file__).with_name('issue_categories.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
print(out['total_confirmed'])
for k, v in sorted(out['categories'].items(), key=lambda kv: -kv[1]['specified']):
    print(f"{k:22} specified {v['specified']:4}  unspecified {v['unspecified']:3}  videos {v['videos']}")
