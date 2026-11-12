#!/usr/bin/env python3
"""Per candidate category: how often the prompt/contract names it (would become a specified contract entity) versus how
often it appears unnamed (would become unspecified), using the C + plug-in run (1,000 videos). Keyword matching, so
approximate. Columns per category:
- episodes_named: episodes (of 200) whose prompt or contract text names the category;
- videos_detected: videos where WeDetect produced a candidate with a category label (absorbed, rejected or excluded);
  named / unnamed split of those videos;
- issues: confirmed V-V issues whose description names the category (appearance/object/background subcategories
  only), split by whether the episode names the category. Issues in unnamed episodes are the rough upper bound of
  issues that would get an unspecified subject; issues in named episodes would mostly stay specified.
Zero model calls. Writes category_yield.json."""
import collections
import json
import re
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / 'vl_vv_full_first200_c_20261110' / 'runs'
CATS = {
    'clothing': (r'\b(shirts?|blouses?|jackets?|coats?|suits?|sweaters?|cardigans?|dress(es)?|gowns?|t-shirts?|tees?|hoodies?|uniforms?|vests?|blazers?|robes?|overalls|jumpsuits?|sweatshirts?|parkas?|outfits?|clothes|clothing|tunics?|kimonos?|tops?)\b',
                 r'衬衫|上衣|外套|夹克|西装|毛衣|开衫|连衣裙|长裙|礼服|T恤|卫衣|大衣|背心|制服|衣领|领口|袖|衣服|服装|着装',
                 {'服装', '夹克衫', '西装', '毛衣', '连衣裙/特定场合的服装', '衬衫', '大衣', '衣服', '商务西装', '运动衫', '背心', '牛仔夹克', '穿着'}),
    'trousers_skirt': (r'\b(trousers|pants|jeans|skirts?|shorts|slacks|leggings)\b', r'裤|裙子|短裙|半身裙', {'裤子', '牛仔裤'}),
    'footwear': (r'\b(shoes?|boots?|sneakers?|sandals?|heels|loafers?|slippers?)\b', r'鞋|靴', {'鞋', '皮鞋', '鞋子', '靴子'}),
    'headwear': (r'\b(hats?|caps?|helmets?|beanies?|hoods?|headbands?|hairpins?|hair clips?|bandanas?|turbans?|headscarf|berets?|bonnets?)\b',
                 r'帽|头盔|头巾|发夹|发饰|发带', {'帽子', '头盔', '无边便帽', '发夹'}),
    'eyewear': (r'\b(glasses|spectacles|sunglasses|goggles|eyeglasses)\b', r'眼镜|墨镜|太阳镜|护目镜', {'眼镜', '太阳镜'}),
    'tie_scarf': (r'\b(ties?|neckties?|bow ?ties?|scarf|scarves|cravats?|shawls?)\b', r'领带|领结|围巾|丝巾|披肩', {'领带', '领结', '围巾'}),
    'jewelry_watch': (r'\b(necklaces?|earrings?|bracelets?|rings?|watch|wristwatch(es)?|pendants?|brooch(es)?|chains?|studs?|jewel(le)?ry|bangles?)\b',
                      r'项链|耳环|耳钉|手镯|手链|戒指|手表|腕表|胸针|吊坠|首饰', {'项链', '耳环', '手镯', '手表', '环/戒指', '时尚配饰'}),
    'belt_badge': (r'\b(belts?|lanyards?|badges?|name tags?|id cards?|suspenders|straps?)\b', r'挂绳|工牌|胸牌|徽章|名牌|腰带|皮带|背带', {'腰带', '带子'}),
    'gloves_apron': (r'\b(gloves?|aprons?|mittens?)\b', r'手套|围裙', {'手套', '围裙'}),
    'bag': (r'\b(bags?|backpacks?|purses?|handbags?|briefcases?|satchels?|totes?)\b', r'背包|手提包|挎包|公文包|书包|手包', {'背包'}),
    'wall_floor_ceiling': (r'\b(walls?|floors?|ceilings?|flooring|tiles?|tiled)\b', r'墙|地板|天花板|瓷砖', {'地板/地面'}),
    'ground': (r'\b(streets?|roads?|pavement|sidewalks?|ground|snow|sand|grass|lawns?|paths?|dirt|gravel|asphalt|cobbles?(tones?)?)\b',
               r'地面|路面|街道|道路|雪地|沙地|草地|草坪|人行道', set()),
    'floor_covering': (r'\b(rugs?|carpets?|carpeting|mats?|doormats?)\b', r'地毯|地垫|脚垫', {'地毯', '红地毯', '地垫', '脚垫', '浴垫', '瑜伽垫'}),
    'trees_plants': (r'\b(trees?|bush(es)?|shrubs?|hedges?|foliage|forest|palms?|vegetation)\b', r'树|灌木|树篱|植被|森林',
                     {'树', 'Background trees', 'Forest trees', '树干'}),
}
SUBCATS = {'character_appearance', 'appearance_drift', 'object_identity', 'object_instability', 'presence_instability',
           'setting_background', 'background_drift', 'instance_count'}
P = {k: re.compile(v[0], re.I) for k, v in CATS.items()}
I = {k: re.compile(v[1]) for k, v in CATS.items()}
stats = {k: collections.Counter() for k in CATS}
named_eps = {k: set() for k in CATS}
for base in sorted(RUNS.iterdir()):
    case = base / 'case'
    p, c = json.loads((case / 'prompt.json').read_text()), json.loads((case / 'contract.json').read_text())
    text = ' '.join([p.get('global_prompt') or ''] + [s.get('text') or '' for s in p['shots']] +
                    [f"{e.get('name', '')} {e.get('description', '')}" for e in c['entity_descriptions'].values()])
    episode = c['episode_id']
    labels = set()
    for inp in (case / 'entities/shots').glob('*/input.json'):
        i = json.loads(inp.read_text())
        labels |= {d['name'] for f in i['frames'] for d in f['detections']}
        labels |= {x['detection']['label'] for x in (i.get('candidate_filter') or {}).get('excluded_detections') or []}
    r = json.loads((base / 'results_with/vv_review/result.json').read_text())
    lab = {e['entity_key']: e.get('label') for e in r.get('entities') or []}
    for k in CATS:
        named = bool(P[k].search(text))
        if named:
            named_eps[k].add(episode)
        if labels & CATS[k][2]:
            stats[k]['videos_detected'] += 1
            stats[k]['videos_detected_named' if named else 'videos_detected_unnamed'] += 1
        for u in r['units']:
            if u['verdict'] != 'confirmed' or u['subcategory'] not in SUBCATS:
                continue
            if I[k].search(u.get('description') or ''):
                uns = any(lab.get(x['entity_key']) == 'unspecified' for x in u.get('entity_refs') or [] if x.get('role') == 'subject')
                stats[k]['issues'] += 1
                stats[k]['issues_named_episode' if named else 'issues_unnamed_episode'] += 1
                stats[k]['issues_already_unspecified'] += uns
out = {k: dict(stats[k], episodes_named=len(named_eps[k])) for k in CATS}
Path(__file__).with_name('category_yield.json').write_text(json.dumps(out, indent=1) + '\n')
print(f"{'category':20} {'eps_named':>9} {'det':>5} {'det_unnamed':>11} {'issues':>6} {'iss_unnamed':>11} {'already_uns':>11}")
for k, v in out.items():
    print(f"{k:20} {v['episodes_named']:9} {v.get('videos_detected', 0):5} {v.get('videos_detected_unnamed', 0):11} {v.get('issues', 0):6} {v.get('issues_unnamed_episode', 0):11} {v.get('issues_already_unspecified', 0):11}")
