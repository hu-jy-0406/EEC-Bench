#!/usr/bin/env python3
"""For each confirmed V-V issue of the C + plug-in run that names a candidate item (worn item, wall/floor/ground part,
floor covering, tree), check whether the prompt names that specific item type: (a) in the subject entity's own contract
name/description, (b) anywhere in the prompt or contract. An issue whose item the prompt does not name would get an
unspecified subject if the item became an entity; one whose item is named would stay specified (the item becomes a
contract entity). Chinese item words of the issue are mapped to English words of the prompt; approximate.
Zero model calls. Writes item_named.json."""
import collections
import json
import re
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / 'vl_vv_full_first200_c_20261110' / 'runs'
# category, Chinese issue word, English prompt words
ITEMS = [
    ('clothing', r'衬衫', r'shirts?|blouses?'), ('clothing', r'T恤', r't-?shirts?|tees?|shirts?'),
    ('clothing', r'外套|大衣', r'coats?|jackets?|overcoats?|parkas?|trench'), ('clothing', r'夹克', r'jackets?|blazers?|coats?'),
    ('clothing', r'西装', r'suits?|blazers?|jackets?|tuxedos?'), ('clothing', r'毛衣|开衫|针织', r'sweaters?|cardigans?|jumpers?|knit\w*|pullovers?'),
    ('clothing', r'连衣裙|长裙|礼服', r'dress(es)?|gowns?'), ('clothing', r'背心|马甲', r'vests?|waistcoats?|tank tops?'),
    ('clothing', r'卫衣', r'hoodies?|sweatshirts?'), ('clothing', r'制服|工作服', r'uniforms?|scrubs|overalls|coveralls'),
    ('clothing', r'上衣', r'tops?|shirts?|blouses?|sweaters?|jackets?|t-?shirts?'),
    ('trousers_skirt', r'裤', r'trousers|pants|jeans|slacks|shorts|leggings'), ('trousers_skirt', r'裙子|短裙|半身裙', r'skirts?|dress(es)?'),
    ('footwear', r'鞋|靴', r'shoes?|boots?|sneakers?|sandals?|heels|loafers?|slippers?|footwear'),
    ('headwear', r'帽|头盔', r'hats?|caps?|beanies?|berets?|helmets?|hoods?|bonnets?|fedoras?'),
    ('headwear', r'头巾|发夹|发饰|发带|发卡', r'headscarf|headscarves|bandanas?|turbans?|hairpins?|hair ?clips?|headbands?|barrettes?|hair (ornament|accessory|piece|bow|ribbon)s?|bows?|ribbons?'),
    ('eyewear', r'眼镜|墨镜|太阳镜|护目镜', r'glasses|spectacles|sunglasses|eyeglasses|goggles'),
    ('tie_scarf', r'领带', r'ties?|neckties?'), ('tie_scarf', r'领结', r'bow ?ties?'),
    ('tie_scarf', r'围巾|丝巾|披肩', r'scarf|scarves|shawls?|stoles?|wraps?'),
    ('jewelry_watch', r'项链|吊坠', r'necklaces?|pendants?|chains?|lockets?'), ('jewelry_watch', r'耳环|耳钉|耳坠', r'earrings?|studs?'),
    ('jewelry_watch', r'手镯|手链', r'bracelets?|bangles?'), ('jewelry_watch', r'戒指', r'rings?'),
    ('jewelry_watch', r'手表|腕表', r'watch(es)?|wristwatch(es)?'), ('jewelry_watch', r'胸针', r'brooch(es)?|pins?'),
    ('belt_badge', r'挂绳|工牌|胸牌|名牌|证件', r'lanyards?|badges?|name ?tags?|id cards?|passes'), ('belt_badge', r'徽章', r'badges?|pins?|insignias?|emblems?|medals?'),
    ('belt_badge', r'腰带|皮带', r'belts?'), ('belt_badge', r'背带', r'suspenders|braces|straps?'),
    ('gloves_apron', r'手套', r'gloves?|mittens?'), ('gloves_apron', r'围裙', r'aprons?'),
    ('bag', r'背包|书包|手提包|挎包|手包|公文包|提包', r'bags?|backpacks?|purses?|handbags?|briefcases?|satchels?|totes?'),
    ('wall_floor_ceiling', r'墙', r'walls?|wallpaper'), ('wall_floor_ceiling', r'地板|木地板', r'floors?|flooring|floorboards?'),
    ('wall_floor_ceiling', r'天花板|吊顶', r'ceilings?'), ('wall_floor_ceiling', r'瓷砖|地砖', r'tiles?|tiled'),
    ('ground', r'地面|路面|街道|道路|马路|人行道', r'ground|streets?|roads?|pavements?|sidewalks?|floors?|paths?|asphalt|cobbles\w*|forecourt|courtyard'),
    ('ground', r'雪地|积雪', r'snow\w*'), ('ground', r'草地|草坪', r'grass\w*|lawns?|meadows?|fields?'), ('ground', r'沙地|沙滩', r'sand\w*|beach(es)?'),
    ('floor_covering', r'地毯|地垫|脚垫', r'rugs?|carpets?|carpeting|mats?|doormats?'),
    ('trees_plants', r'树|灌木|树篱|植被|森林', r'trees?|bush(es)?|shrubs?|hedges?|foliage|forest|palms?|vegetation|woods'),
]
WORN = {'clothing', 'trousers_skirt', 'footwear', 'headwear', 'eyewear', 'tie_scarf', 'jewelry_watch', 'belt_badge', 'gloves_apron', 'bag'}
SUBCATS = {'character_appearance', 'appearance_drift', 'object_identity', 'object_instability', 'presence_instability',
           'setting_background', 'background_drift', 'instance_count'}
CI = [(cat, re.compile(zh), re.compile(r'\b(' + en + r')\b', re.I)) for cat, zh, en in ITEMS]
stats = collections.defaultdict(collections.Counter)
examples = collections.defaultdict(list)
issue_level = collections.Counter()
per_issue = []
for base in sorted(RUNS.iterdir()):
    case = base / 'case'
    p, c = json.loads((case / 'prompt.json').read_text()), json.loads((case / 'contract.json').read_text())
    eds = c['entity_descriptions']
    whole = ' '.join([p.get('global_prompt') or ''] + [s.get('text') or '' for s in p['shots']] +
                     [f"{e.get('name', '')} {e.get('description', '')}" for e in eds.values()])
    r = json.loads((base / 'results_with/vv_review/result.json').read_text())
    ent = {e['entity_key']: e for e in r.get('entities') or []}
    for u in r['units']:
        if u['verdict'] != 'confirmed' or u['subcategory'] not in SUBCATS:
            continue
        text = u.get('description') or ''
        subs = [ent.get(x['entity_key'], {}) for x in u.get('entity_refs') or [] if x.get('role') == 'subject']
        if any(s.get('label') == 'unspecified' for s in subs):
            issue_level['already_unspecified'] += 1
            continue
        own = []
        kinds = set()
        for s in subs:
            ce = eds.get(str(s.get('prompt_entity_id')), {})
            kinds.add(ce.get('label'))
            own.append(f"{s.get('name', '')} {ce.get('name', '')} {ce.get('description', '')}")
        own = ' '.join(own)
        hit = []
        for cat, zh, en in CI:
            if not zh.search(text):
                continue
            if cat in WORN and 'character' not in kinds:
                continue  # worn items only for issues about a character
            hit.append((cat, bool(en.search(own)), bool(en.search(whole))))
        if not hit:
            continue
        cats = {}
        for cat, in_own, in_whole in hit:  # per category: named if any of its words matched is named
            a, b = cats.get(cat, (True, True))
            cats[cat] = (a and in_own, b and in_whole)
        for cat, (in_own, in_whole) in cats.items():
            st = stats[cat]
            st['issues'] += 1
            st['named_in_subject'] += in_own
            st['named_in_prompt'] += in_whole
            st['unnamed_anywhere'] += not in_whole
            if not in_whole and len(examples[cat]) < 4:
                examples[cat].append(f"{base.name} {[s.get('name') for s in subs]} {text[:110]}")
        per_issue.append({cat: own_named for cat, (own_named, _) in cats.items()})
        issue_level['issues_with_candidate_item'] += 1
        issue_level['issues_with_unnamed_item'] += any(not w for _, w in cats.values())
        issue_level['issues_with_item_unnamed_for_subject'] += any(not o for o, _ in cats.values())
SETS = dict(all=set(CI_CATS := {c for c, _, _ in ITEMS}),
            worn_all=WORN, clothing_only={'clothing'},
            favourable={'belt_badge', 'ground', 'wall_floor_ceiling', 'headwear', 'eyewear', 'tie_scarf', 'trousers_skirt', 'trees_plants', 'floor_covering'},
            place_parts={'wall_floor_ceiling', 'ground', 'floor_covering', 'trees_plants'})
scenario = {k: sum(1 for d in per_issue if any(c in v and not named for c, named in d.items())) for k, v in SETS.items()}
issue_level['scenario_issues_moving_to_unspecified'] = scenario
out = dict(issue_level=dict(issue_level), categories={k: dict(v) for k, v in stats.items()}, examples=examples)
Path(__file__).with_name('item_named.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
print(out['issue_level'])
print(f"{'category':20} {'issues':>6} {'named_subj':>10} {'named_prompt':>12} {'unnamed':>8}")
for k, v in sorted(out['categories'].items(), key=lambda kv: -kv[1]['unnamed_anywhere']):
    print(f"{k:20} {v['issues']:6} {v['named_in_subject']:10} {v['named_in_prompt']:12} {v['unnamed_anywhere']:8}")
for k in ('headwear', 'belt_badge', 'ground', 'wall_floor_ceiling', 'clothing', 'jewelry_watch'):
    for e in examples.get(k, [])[:2]:
        print(' ', k, e)
